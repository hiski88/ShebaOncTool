"""Tool 4 - view a final schedule and create calendar invitations.

Managers publish the official central schedule in Tool 3.
Tool 4 may read that official schedule or a temporary upload used only in the
current Streamlit session. Temporary uploads are never written to Drive or to
the final-schedule index.
"""
from __future__ import annotations

from final_schedule_reader import download_final_schedule, latest_final_schedule
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


def _load_central_schedule(st, app_module, year: int, month: int, config: dict):
    schedule_file = latest_final_schedule(st, year, month)
    if schedule_file is None:
        return None

    stored_name = str(schedule_file.get("name", "") or "")
    version = int(schedule_file.get("version", 0) or 0)
    content = download_final_schedule(st, str(schedule_file.get("id", "") or ""))
    workbook = app_module.read_schedule_workbook(content, stored_name)
    names = sorted(set(app_module.infer_employee_names(workbook, config)))
    return {
        "workbook": workbook,
        "names": names,
        "source_label": f"{stored_name} (גרסה V{version})",
        "source_key": f"central_{year}_{month}_{version}",
        "temporary": False,
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
        "temporary": True,
    }


def _render_schedule_view(st, records, employee: str) -> None:
    st.subheader("צפייה בלו״ז")
    employee_records = records[records["employee"] == employee].copy()
    if employee_records.empty:
        st.info("לא נמצאו שיבוצים עבור העובד/ת שנבחר/ה.")
        return

    preferred = [
        column
        for column in ("date", "day", "task_label", "subtype")
        if column in employee_records.columns
    ]
    display = employee_records[preferred].copy() if preferred else employee_records.copy()
    rename = {
        "date": "תאריך",
        "day": "יום",
        "task_label": "שיבוץ",
        "subtype": "פירוט",
    }
    display = display.rename(columns=rename)
    if "פירוט" in display.columns and display["פירוט"].fillna("").astype(str).str.strip().eq("").all():
        display = display.drop(columns=["פירוט"])
    st.dataframe(display, width="stretch", hide_index=True)


def install(app_module) -> None:
    if getattr(app_module, "_tool4_central_schedule_installed", False):
        return

    def tool_calendar_from_schedule() -> None:
        st = app_module.st
        app_module.render_header(
            "4. צפייה בלו״ז ויצירת זימונים",
            "אפשר להשתמש בסידור הרשמי שנשמר על ידי מנהל/ת, או להעלות קובץ זמני לצפייה וליצירת ICS בלבד.",
        )

        year, month = app_module.month_selector("calendar_final_schedule", offset=0)
        config = _session_calendar_config(app_module, st)
        employee_mode = isinstance(st.session_state.get(IDENTIFIED_WORKER_SESSION_KEY), dict)

        source = st.radio(
            "מקור הסידור",
            ["סידור רשמי שמור", "העלאה זמנית"],
            horizontal=True,
            key="tool4_schedule_source",
        )

        schedule_data = None
        if source == "סידור רשמי שמור":
            try:
                schedule_data = _load_central_schedule(st, app_module, year, month, config)
            except Exception as exc:
                st.error(f"לא ניתן לקרוא את ארכיון הסידורים המרכזי: {exc}")
                return

            if schedule_data is None:
                st.info(
                    f"עדיין לא נשמר סידור רשמי לחודש {month:02d}-{year:04d}. "
                    "מנהל/ת יכול/ה לפרסם אותו בכלי 3, או שניתן לבחור העלאה זמנית."
                )
                return
            st.success(f"נטען הסידור הרשמי: {schedule_data['source_label']}.")
        else:
            st.info(
                "הקובץ הזמני משמש רק לצפייה וליצירת זימונים במהלך העבודה הנוכחית. "
                "הוא אינו נשמר ב-Google Drive ואינו משנה את הסידור הרשמי."
            )
            uploaded = st.file_uploader(
                "העלאת לוח זמנים זמני",
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
            st.success(f"נטען קובץ זמני: {schedule_data['source_label']}.")

        names = schedule_data["names"]
        workbook = schedule_data["workbook"]
        source_key = schedule_data["source_key"]

        if not names:
            st.error(
                "לא ניתן לזהות שמות עובדים מהסידור באופן אמין. "
                "יש לבדוק שהקובץ הוא קובץ הסידור המקורי ובמבנה הנתמך."
            )
            return

        if employee_mode:
            employee = _identified_employee_name(st, names)
            if not employee:
                st.error(
                    "לא ניתן להתאים באופן אמין את המשתמש/ת המחובר/ת לשם בסידור. "
                    "מטעמי פרטיות לא יוצגו נתונים של עובדים אחרים."
                )
                return
            st.caption(f"המידע מוצג עבור: {employee}")
        else:
            employee = st.selectbox(
                "בחירת עובד/ת",
                names,
                index=0,
                key=f"calendar_employee_{source_key}",
            )

        try:
            records = app_module.parse_schedule(workbook, config, names)
        except Exception as exc:
            st.error(f"פענוח הסידור נכשל: {exc}")
            return

        _render_schedule_view(st, records, employee)

        candidate_records, events, event_config = _calendar_candidate_events(
            app_module,
            records,
            employee,
            config,
        )

        st.subheader("אירועים לזימון")
        if candidate_records.empty:
            st.info("לא נמצאו תורנויות או אירועים מיוחדים עבור העובד/ת.")
        else:
            display_columns = [
                column for column in ("date", "day", "task_label", "subtype")
                if column in candidate_records.columns
            ]
            display = candidate_records[display_columns].rename(
                columns={"date": "תאריך", "day": "יום", "task_label": "אירוע", "subtype": "פירוט"}
            )
            if "פירוט" in display.columns and display["פירוט"].fillna("").astype(str).str.strip().eq("").all():
                display = display.drop(columns=["פירוט"])
            st.dataframe(display, width="stretch", hide_index=True)

        if not events:
            st.info("אין כרגע אירועים לשמירה ביומן.")
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
                disabled=[column for column in preview.columns if column != "להוסיף ליומן"],
                column_config={
                    "להוסיף ליומן": st.column_config.CheckboxColumn("להוסיף ליומן"),
                },
                key=f"calendar_event_selection_{source_key}_{employee}",
            )
            selected_events = [
                event
                for event, keep in zip(events, edited_preview["להוסיף ליומן"].tolist())
                if bool(keep)
            ]
            st.caption(f"נבחרו {len(selected_events)} מתוך {len(events)} אירועים.")

        ics = app_module.events_to_ics(
            selected_events,
            event_config.get("timezone", "Asia/Jerusalem"),
        )
        st.download_button(
            "הורדת קובץ ICS",
            data=ics,
            file_name=f"לוז_{employee}_{year}_{month:02d}.ics",
            mime="text/calendar",
            width="stretch",
            disabled=not selected_events,
        )

    app_module.tool_calendar = tool_calendar_from_schedule
    app_module._tool4_central_schedule_installed = True
