"""Tool 4 - create calendar invitations from a monthly schedule.

Tool 3 owns monthly-schedule browsing and manager-only publishing.
Tool 4 is action-focused:
- use a stored official schedule version, or a temporary local upload;
- resolve the relevant employee;
- preview only the events that can become calendar invitations;
- export selected events as ICS.

Temporary uploads are never persisted to Google Drive or the schedule index.
"""
from __future__ import annotations

from final_schedule_reader import download_final_schedule, list_final_schedules
from tool3_minimal_overrides import _calendar_candidate_events, _session_calendar_config


IDENTIFIED_WORKER_SESSION_KEY = "medstaff_identified_worker_v1"


def _normalize_name(value: object) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def _identified_employee_name(st, names: list[str]) -> str | None:
    worker = st.session_state.get(IDENTIFIED_WORKER_SESSION_KEY)
    if not isinstance(worker, dict):
        return None

    normalized_names = [(_normalize_name(name), name) for name in names]
    full_name = _normalize_name(worker.get("full_name", ""))
    first_name = _normalize_name(worker.get("first_name", ""))

    if full_name:
        exact_full = [name for normalized, name in normalized_names if normalized == full_name]
        if len(exact_full) == 1:
            return exact_full[0]

    if first_name:
        exact_first = [name for normalized, name in normalized_names if normalized == first_name]
        if len(exact_first) == 1:
            return exact_first[0]

    return ""


def _load_stored_schedule(st, app_module, schedule_file: dict, config: dict):
    stored_name = str(schedule_file.get("name", "") or "")
    version = int(schedule_file.get("version", 0) or 0)
    content = download_final_schedule(st, str(schedule_file.get("id", "") or ""))
    workbook = app_module.read_schedule_workbook(content, stored_name)
    names = sorted(set(app_module.infer_employee_names(workbook, config)))
    return {
        "workbook": workbook,
        "names": names,
        "source_label": f"{stored_name} (V{version})",
        "source_key": f"stored_{schedule_file.get('id', '')}_{version}",
    }


def _load_temporary_schedule(uploaded, app_module, config: dict):
    content = uploaded.getvalue()
    filename = str(uploaded.name or "temporary_schedule")
    workbook = app_module.read_schedule_workbook(content, filename)
    names = sorted(set(app_module.infer_employee_names(workbook, config)))
    return {
        "workbook": workbook,
        "names": names,
        "source_label": filename,
        "source_key": f"temporary_{filename}_{len(content)}",
    }


def install(app_module) -> None:
    if getattr(app_module, "_tool4_central_schedule_installed", False):
        return

    def tool_calendar_from_schedule() -> None:
        st = app_module.st
        app_module.render_header(
            "4. יצירת זימון ליומן",
            "בחירת לו״ז קיים או העלאה זמנית, בחירת האירועים הרצויים והפקת קובץ ICS ליומן.",
        )

        config = _session_calendar_config(app_module, st)
        employee_mode = isinstance(st.session_state.get(IDENTIFIED_WORKER_SESSION_KEY), dict)

        source = st.radio(
            "מקור הלו״ז",
            ["לו״ז שמור", "העלאה זמנית"],
            horizontal=True,
            key="tool4_schedule_source",
        )

        schedule_data = None
        selected_year = None
        selected_month = None

        if source == "לו״ז שמור":
            year, month = app_module.month_selector("calendar_final_schedule", offset=0)
            selected_year, selected_month = year, month

            try:
                schedules = list_final_schedules(st, year, month)
            except Exception as exc:
                st.error(f"לא ניתן לקרוא את ארכיון הלו״זים: {exc}")
                return

            if not schedules:
                st.info(
                    f"לא נמצא לו״ז שמור עבור {month:02d}-{year:04d}. "
                    "אפשר לבחור חודש אחר או להשתמש בהעלאה זמנית."
                )
                return

            labels = []
            by_label = {}
            for item in schedules:
                version = int(item.get("version", 0) or 0)
                name = str(item.get("name", "") or "")
                label = f"V{version} - {name}"
                labels.append(label)
                by_label[label] = item

            selected_label = st.selectbox(
                "גרסת לו״ז",
                labels,
                index=0,
                key=f"tool4_saved_version_{year}_{month}",
            )
            try:
                schedule_data = _load_stored_schedule(
                    st, app_module, by_label[selected_label], config
                )
            except Exception as exc:
                st.error(f"לא ניתן לטעון את הלו״ז שנבחר: {exc}")
                return
            st.caption(f"מקור: {schedule_data['source_label']}")
        else:
            st.info(
                "הקובץ משמש רק ליצירת הזימון במהלך העבודה הנוכחית. "
                "הוא אינו נשמר במערכת ואינו משנה אף לו״ז רשמי."
            )
            uploaded = st.file_uploader(
                "העלאת לו״ז זמני",
                type=["xls", "xlsx", "xlsm"],
                key="tool4_temporary_schedule",
            )
            if uploaded is None:
                return
            try:
                schedule_data = _load_temporary_schedule(uploaded, app_module, config)
            except Exception as exc:
                st.error(f"לא ניתן לקרוא את הקובץ הזמני: {exc}")
                return
            st.caption(f"מקור זמני: {schedule_data['source_label']}")

        names = schedule_data["names"]
        workbook = schedule_data["workbook"]
        source_key = schedule_data["source_key"]

        if not names:
            st.error("לא ניתן לזהות שמות עובדים מהלו״ז באופן אמין.")
            return

        display_employee = None
        if employee_mode:
            employee = _identified_employee_name(st, names)
            if not employee:
                st.error(
                    "לא ניתן להתאים את המשתמש/ת המחובר/ת לשם בלו״ז. "
                    "מטעמי פרטיות לא יוצגו נתונים של עובדים אחרים."
                )
                return
            worker = st.session_state.get(IDENTIFIED_WORKER_SESSION_KEY, {})
            display_employee = str(worker.get("full_name", "") or employee).strip()
            st.caption(f"יצירת הזימון עבור: {display_employee}")
        else:
            employee = st.selectbox(
                "בחירת עובד/ת",
                names,
                index=0,
                key=f"calendar_employee_{source_key}",
            )
            display_employee = employee

        try:
            records = app_module.parse_schedule(workbook, config, names)
        except Exception as exc:
            st.error(f"פענוח הלו״ז נכשל: {exc}")
            return

        candidate_records, events, event_config = _calendar_candidate_events(
            app_module,
            records,
            employee,
            config,
        )

        st.subheader("אירועים שזוהו")
        if candidate_records.empty:
            st.info("לא נמצאו תורנויות או אירועים מתאימים ליצירת זימון.")
            selected_events = []
        else:
            display_columns = [
                column
                for column in ("date", "day", "task_label", "subtype")
                if column in candidate_records.columns
            ]
            display = candidate_records[display_columns].rename(
                columns={
                    "date": "תאריך",
                    "day": "יום",
                    "task_label": "אירוע",
                    "subtype": "פירוט",
                }
            )
            if (
                "פירוט" in display.columns
                and display["פירוט"].fillna("").astype(str).str.strip().eq("").all()
            ):
                display = display.drop(columns=["פירוט"])
            st.dataframe(display, width="stretch", hide_index=True)

            if not events:
                st.info("אין כרגע אירועים שניתן לייצא ליומן.")
                selected_events = []
            else:
                event_table = app_module.event_dataframe(events)
                preview = event_table[["תאריך", "אירוע", "התחלה", "סיום"]].copy()
                preview.insert(0, "להוסיף ליומן", True)
                edited_preview = st.data_editor(
                    preview,
                    hide_index=True,
                    width="stretch",
                    column_order=["סיום", "התחלה", "אירוע", "תאריך", "להוסיף ליומן"],
                    disabled=[
                        column
                        for column in preview.columns
                        if column != "להוסיף ליומן"
                    ],
                    column_config={
                        "להוסיף ליומן": st.column_config.CheckboxColumn("להוסיף ליומן"),
                    },
                    key=f"calendar_event_selection_{source_key}_{employee}",
                )
                selected_events = [
                    event
                    for event, keep in zip(
                        events, edited_preview["להוסיף ליומן"].tolist()
                    )
                    if bool(keep)
                ]
                st.caption(f"נבחרו {len(selected_events)} מתוך {len(events)} אירועים.")

        ics = app_module.events_to_ics(
            selected_events,
            event_config.get("timezone", "Asia/Jerusalem"),
        )

        if selected_year is not None and selected_month is not None:
            filename = f"לוז_{display_employee}_{selected_year}_{selected_month:02d}.ics"
        else:
            filename = f"לוז_{display_employee}.ics"

        st.download_button(
            "הורדת קובץ ICS",
            data=ics,
            file_name=filename,
            mime="text/calendar",
            width="stretch",
            disabled=not selected_events,
        )

    app_module.tool_calendar = tool_calendar_from_schedule
    app_module._tool4_central_schedule_installed = True
