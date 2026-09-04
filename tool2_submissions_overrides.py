"""Tool 2: read monthly preference submissions directly from Google Sheets."""
from __future__ import annotations

from collections import Counter

import pandas as pd

from google_sheets_submissions import configured, create_planning_sheet, read_submissions


LEGEND_HTML = """
<div dir="rtl" style="margin:0.25rem 0 0.8rem 0;line-height:2.2;">
  <b>מקרא לכרטיסיית התכנון:</b>
  <span style="background:#ff8a8a;border:1px solid #d95f5f;padding:4px 9px;border-radius:5px;margin:0 4px;"><b>XX</b> חופש</span>
  <span style="background:#ffbf69;border:1px solid #d9943e;padding:4px 9px;border-radius:5px;margin:0 4px;"><b>½X</b> חסימת חצי וגם מלאה</span>
  <span style="background:#ffe66d;border:1px solid #d5bd38;padding:4px 9px;border-radius:5px;margin:0 4px;"><b>X</b> חסימת מלאה בלבד</span>
  <span style="background:#8bd17c;border:1px solid #58a64a;padding:4px 9px;border-radius:5px;margin:0 4px;"><b>V</b> מעוניין בתורנות</span>
  <span style="background:#ffffff;border:1px solid #bdbdbd;padding:4px 9px;border-radius:5px;margin:0 4px;">ריק - לא דווחה מגבלה או העדפה</span>
</div>
"""


def install(app_module) -> None:
    if getattr(app_module, "_tool2_submissions_override_installed", False):
        return

    def tool_manager_from_sheets() -> None:
        st = app_module.st
        app_module.render_header(
            "2. ריכוז העדפות ובניית לוז",
            "בחירת חודש מציגה אוטומטית את כל ההגשות שנקלטו מהצוות.",
        )
        year, month = app_module.month_selector("manager", offset=1)

        if not configured(st):
            st.error("חיבור Google Sheets אינו מוגדר באפליקציה.")
            return

        try:
            submissions = read_submissions(st, year, month)
        except Exception as exc:
            st.error(f"לא ניתן לקרוא את ההגשות מ-Google Sheets: {exc}")
            return

        month_display = f"{month:02d}-{year:04d}"
        if not submissions:
            st.info(f"לא נמצאו הגשות לחודש {month_display}.")
            return

        counts = Counter(item["שם עובד"] for item in submissions)
        unique_employees = len(counts)
        duplicate_names = [name for name, count in counts.items() if count > 1]

        st.success(
            f"נמצאו {len(submissions)} הגשות של {unique_employees} עובדים לחודש {month_display}."
        )

        if duplicate_names:
            details = ", ".join(f"{name} ({counts[name]})" for name in duplicate_names)
            st.warning(f"זוהו הגשות כפולות: {details}")

        st.markdown(LEGEND_HTML, unsafe_allow_html=True)

        # Keep the same submission-selection behavior as before, but expose only
        # operational metadata in the planner UI. Sensitive preference details
        # remain in memory and are used only when the planner creates the sheet.
        display_rows = []
        seen = Counter()
        for submission_index, item in enumerate(submissions):
            name = item["שם עובד"]
            seen[name] += 1
            count = counts[name]
            is_newest_for_name = seen[name] == 1
            duplicate_status = ""
            if count > 1:
                duplicate_status = f"{seen[name]} מתוך {count}"
                if is_newest_for_name:
                    duplicate_status += " - החדשה ביותר"

            display_rows.append(
                {
                    "_submission_index": submission_index,
                    "כפילות": duplicate_status,
                    "שם עובד": name,
                    "זמן הגשה": item["זמן הגשה"],
                    "לכלול בתכנון": is_newest_for_name,
                }
            )

        st.subheader("בחירת הגשות לתכנון")
        selected_table = st.data_editor(
            pd.DataFrame(display_rows),
            width="stretch",
            hide_index=True,
            disabled=["זמן הגשה", "שם עובד", "כפילות"],
            column_order=["לכלול בתכנון", "זמן הגשה", "שם עובד", "כפילות"],
            column_config={
                "_submission_index": None,
                "לכלול בתכנון": st.column_config.CheckboxColumn("לכלול בתכנון"),
            },
            key=f"manager_submission_selection_{year}_{month}",
        )

        selected_mask = selected_table["לכלול בתכנון"].fillna(False).astype(bool)
        selected_rows = selected_table[selected_mask].copy()
        selected_count = len(selected_rows)
        st.caption(
            f"נבחרו {selected_count} מתוך {len(submissions)} הגשות. "
            "בכפילות עם שם זהה מסומנת אוטומטית רק ההגשה החדשה ביותר, וניתן לשנות ידנית."
        )

        selected_names = [str(name).strip() for name in selected_rows["שם עובד"].tolist()]
        selected_name_counts = Counter(selected_names)
        duplicate_selected = [name for name, count in selected_name_counts.items() if name and count > 1]
        if duplicate_selected:
            st.warning(
                "לפני יצירת כרטיסיית התכנון יש להשאיר הגשה אחת בלבד לכל שם זהה: "
                + ", ".join(duplicate_selected)
            )

        can_create = selected_count > 0 and not duplicate_selected
        if st.button(
            "צור כרטיסיית תכנון",
            type="primary",
            width="stretch",
            disabled=not can_create,
            key=f"create_planning_sheet_{year}_{month}",
        ):
            selected_submissions = []
            for _, row in selected_rows.iterrows():
                source = submissions[int(row["_submission_index"])]
                selected_submissions.append(
                    {
                        "שם עובד": str(source.get("שם עובד", "") or "").strip(),
                        "חסימת תורנות מלאה": str(source.get("חסימת תורנות מלאה", "") or "").strip(),
                        "חסימת תורנות חצי": str(source.get("חסימת תורנות חצי", "") or "").strip(),
                        "חופשים": str(source.get("חופשים", "") or "").strip(),
                        "מעוניין בתורנות": str(source.get("מעוניין בתורנות", "") or "").strip(),
                        "הערה כללית": str(source.get("הערה כללית", "") or "").strip(),
                    }
                )
            try:
                month_table = app_module.build_month_table(year, month)
                title = create_planning_sheet(
                    st,
                    year,
                    month,
                    month_table.to_dict("records"),
                    selected_submissions,
                )
                st.success(f"הכרטיסייה '{title}' נוצרה בהצלחה ב-Google Sheet.")
            except Exception as exc:
                st.error(f"לא ניתן ליצור את כרטיסיית התכנון: {exc}")

    app_module.tool_manager = tool_manager_from_sheets
    app_module._tool2_submissions_override_installed = True
