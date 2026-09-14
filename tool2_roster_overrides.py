"""Tool 2 roster view: Workers is the source of truth, submissions enrich it."""
from __future__ import annotations

from calendar import monthrange
from collections import Counter
from datetime import date

import pandas as pd

import tool2_submissions_overrides as tool2
import tool6_workers as workers_store


def _worker_name(worker: dict[str, object]) -> str:
    return " ".join(
        part
        for part in (
            str(worker.get("first_name", "") or "").strip(),
            str(worker.get("last_name", "") or "").strip(),
        )
        if part
    ).strip()


def _is_active_for_month(worker: dict[str, object], year: int, month: int) -> bool:
    if str(worker.get("status", "") or "").strip() != "פעיל":
        return False
    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])
    department_start = worker.get("department_start")
    activity_end = worker.get("activity_end")
    if isinstance(department_start, date) and department_start > month_end:
        return False
    if isinstance(activity_end, date) and activity_end < month_start:
        return False
    return True


def _period_label(period: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("period_type", "framework", "subunit"):
        value = str(period.get(key, "") or "").strip()
        if value and value not in parts:
            parts.append(value)
    return " - ".join(parts)


def _worker_period_summary(worker_id: str, periods: list[dict[str, object]], year: int, month: int) -> str:
    month_start = date(year, month, 1)
    month_end = date(year, month, monthrange(year, month)[1])
    labels: list[str] = []
    for period in periods:
        if str(period.get("worker_id", "") or "") != worker_id:
            continue
        start = period.get("start_date")
        end = period.get("end_date")
        if not isinstance(start, date) or not isinstance(end, date):
            continue
        if start > month_end or end < month_start:
            continue
        label = _period_label(period)
        if label and label not in labels:
            labels.append(label)
    return " + ".join(labels)


def _legacy_submission_worker_id(
    submission: dict[str, str],
    roster: list[dict[str, object]],
) -> str:
    """Best-effort compatibility for rows created before Worker ID existed."""
    if str(submission.get("Worker ID", "") or "").strip():
        return str(submission.get("Worker ID", "") or "").strip()
    submitted_name = str(submission.get("שם עובד", "") or "").strip().casefold()
    if not submitted_name:
        return ""

    exact = [w for w in roster if _worker_name(w).casefold() == submitted_name]
    if len(exact) == 1:
        return str(exact[0].get("worker_id", "") or "")

    first_name = [
        w
        for w in roster
        if str(w.get("first_name", "") or "").strip().casefold() == submitted_name
    ]
    if len(first_name) == 1:
        return str(first_name[0].get("worker_id", "") or "")
    return ""


def _latest_submissions_by_worker(
    submissions: list[dict[str, str]],
    roster: list[dict[str, object]],
) -> tuple[dict[str, dict[str, str]], Counter]:
    latest: dict[str, dict[str, str]] = {}
    counts: Counter = Counter()
    # read_submissions is newest-first, so the first mapped row is the latest.
    for item in submissions:
        worker_id = _legacy_submission_worker_id(item, roster)
        if not worker_id:
            continue
        counts[worker_id] += 1
        if worker_id not in latest:
            latest[worker_id] = item
    return latest, counts


def install(app_module) -> None:
    if getattr(app_module, "_tool2_roster_override_installed", False):
        return

    def tool_manager_from_roster() -> None:
        st = app_module.st
        app_module.render_header(
            "2. ריכוז העדפות ובניית לוז",
            "רשימת העובדים הפעילים היא בסיס התכנון; ההעדפות שהוגשו מצטרפות אליה לפי Worker ID.",
        )

        if not tool2._planner_access_granted(st):
            return

        year, month = app_module.month_selector("manager", offset=1)
        if not tool2.configured(st):
            st.error("חיבור Google Sheets אינו מוגדר באפליקציה.")
            return

        try:
            all_workers = workers_store._worker_records(workers_store._read_worker_rows(st))
            periods = workers_store._period_records(workers_store._read_period_rows(st))
            submissions = tool2.read_submissions(st, year, month)
        except Exception as exc:
            st.error(f"לא ניתן לטעון את נתוני התכנון: {exc}")
            return

        roster = [worker for worker in all_workers if _is_active_for_month(worker, year, month)]
        roster.sort(
            key=lambda item: (
                str(item.get("last_name", "") or "").casefold(),
                str(item.get("first_name", "") or "").casefold(),
            )
        )
        month_display = f"{month:02d}-{year:04d}"
        if not roster:
            st.info(f"לא נמצאו עובדים פעילים לחודש {month_display}.")
            return

        latest_by_worker, submission_counts = _latest_submissions_by_worker(submissions, roster)
        submitted_count = sum(1 for worker in roster if str(worker.get("worker_id")) in latest_by_worker)
        missing_count = len(roster) - submitted_count

        st.success(f"{len(roster)} עובדים פעילים לחודש {month_display}; {submitted_count} הגישו העדפות.")
        if missing_count:
            st.warning(f"{missing_count} עובדים עדיין לא הגישו העדפות לחודש זה.")

        st.markdown(tool2.LEGEND_HTML, unsafe_allow_html=True)
        display_rows = []
        for worker in roster:
            worker_id = str(worker.get("worker_id", "") or "")
            submission = latest_by_worker.get(worker_id)
            display_rows.append(
                {
                    "Worker ID": worker_id,
                    "שם עובד": _worker_name(worker),
                    "מסלול": str(worker.get("track", "") or ""),
                    "כשירות תורנויות": str(worker.get("eligibility", "") or ""),
                    "תקופה / רוטציה": _worker_period_summary(worker_id, periods, year, month),
                    "סטטוס הגשה": "הוגש" if submission else "לא הוגש",
                    "זמן הגשה אחרון": str(submission.get("זמן הגשה", "") if submission else ""),
                    "מספר הגשות": int(submission_counts.get(worker_id, 0)),
                    "לכלול בתכנון": True,
                }
            )

        st.subheader("מצבת עובדים לחודש")
        selected_table = st.data_editor(
            pd.DataFrame(display_rows),
            width="stretch",
            hide_index=True,
            disabled=[
                "Worker ID",
                "שם עובד",
                "מסלול",
                "כשירות תורנויות",
                "תקופה / רוטציה",
                "סטטוס הגשה",
                "זמן הגשה אחרון",
                "מספר הגשות",
            ],
            column_order=[
                "לכלול בתכנון",
                "מספר הגשות",
                "זמן הגשה אחרון",
                "סטטוס הגשה",
                "תקופה / רוטציה",
                "כשירות תורנויות",
                "מסלול",
                "שם עובד",
                "Worker ID",
            ],
            column_config={
                "לכלול בתכנון": st.column_config.CheckboxColumn("לכלול בתכנון"),
            },
            key=f"manager_roster_selection_{year}_{month}",
        )

        selected_mask = selected_table["לכלול בתכנון"].fillna(False).astype(bool)
        selected_rows = selected_table[selected_mask].copy()
        st.caption(f"נבחרו {len(selected_rows)} מתוך {len(roster)} עובדים לתכנון.")

        create_clicked = st.button(
            "צור כרטיסיית תכנון",
            type="primary",
            width="stretch",
            disabled=selected_rows.empty,
            key=f"create_roster_planning_sheet_{year}_{month}",
        )
        if not create_clicked:
            return

        selected_submissions = []
        for _, row in selected_rows.iterrows():
            worker_id = str(row["Worker ID"])
            source = latest_by_worker.get(worker_id, {})
            selected_submissions.append(
                {
                    "Worker ID": worker_id,
                    "שם עובד": str(row["שם עובד"]),
                    "חסימת תורנות מלאה": str(source.get("חסימת תורנות מלאה", "") or ""),
                    "חסימת תורנות חצי": str(source.get("חסימת תורנות חצי", "") or ""),
                    "חופשים": str(source.get("חופשים", "") or ""),
                    "מעוניין בתורנות": str(source.get("מעוניין בתורנות", "") or ""),
                    "הערה כללית": str(source.get("הערה כללית", "") or ""),
                }
            )

        try:
            month_table = app_module.build_month_table(
                year,
                month,
                special_days=app_module.CONFIG.get("special_days", {}),
            )
            title = tool2.create_planning_sheet(
                st,
                year,
                month,
                month_table.to_dict("records"),
                selected_submissions,
            )
            st.success(f"הכרטיסייה '{title}' נוצרה בהצלחה ב-Google Sheet.")
        except Exception as exc:
            st.error(f"לא ניתן ליצור את כרטיסיית התכנון: {exc}")

    app_module.tool_manager = tool_manager_from_roster
    app_module._tool2_roster_override_installed = True
