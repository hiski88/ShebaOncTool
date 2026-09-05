"""Minimal employee-facing calendar export flow.

This tool reads a final roster, lets an employee select relevant events, and
downloads an ICS file. In a later stage it will read the centrally stored final
schedule instead of requiring each employee to upload the source file.
"""
from __future__ import annotations

import pandas as pd


def install(app_module) -> None:
    if getattr(app_module, "_tool3_minimal_installed", False):
        return

    def tool_calendar_minimal() -> None:
        st = app_module.st
        app_module.render_header(
            "4. יצירת זימונים ליומן",
            "מעלים את הלוז הסופי, בוחרים עובד/ת ומורידים קובץ ICS עם תורנויות ואירועים חשובים בלבד.",
        )

        uploaded = st.file_uploader(
            "העלאת לוז סופי",
            type=["xls", "xlsx", "xlsm"],
            key="final_schedule",
        )
        if uploaded is None:
            st.info("המערכת תומכת ב-XLS וב-XLSX. ב-XLSX זיהוי עיצובי מחיקה אמין יותר.")
            return

        try:
            workbook = app_module.read_schedule_workbook(uploaded.getvalue(), uploaded.name)
            names = sorted(set(app_module.infer_employee_names(workbook, app_module.CONFIG)))
        except Exception as exc:
            st.error(f"לא ניתן לקרוא את הלוז: {exc}")
            return

        if not names:
            st.error(
                "לא ניתן לזהות את שמות העובדים מהלוז באופן אמין. "
                "יש לבדוק שהקובץ הוא קובץ הלוז המקורי ובמבנה הנתמך."
            )
            return

        employee = st.selectbox("בחירת עובד/ת", names, key="calendar_employee")

        try:
            records = app_module.parse_schedule(workbook, app_module.CONFIG, names)
        except Exception as exc:
            st.error(f"פענוח הלוז נכשל: {exc}")
            return

        candidate_records, events, event_config = app_module.calendar_candidate_events(records, employee)

        st.subheader("אירועים שזוהו")
        if candidate_records.empty:
            st.info("לא נמצאו תורנויות או אירועים מיוחדים עבור העובד/ת שנבחר/ה.")
        else:
            display_columns = ["date", "day", "task_label", "subtype"]
            display = candidate_records[display_columns].rename(
                columns={"date": "תאריך", "day": "יום", "task_label": "אירוע", "subtype": "פירוט"}
            )
            if "פירוט" in display.columns and display["פירוט"].fillna("").astype(str).str.strip().eq("").all():
                display = display.drop(columns=["פירוט"])
            st.dataframe(display, width="stretch", hide_index=True)

        st.subheader("אירועים לשמירה ביומן")
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
                key=f"calendar_event_selection_{employee}",
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
            file_name=f"לוז_{employee}.ics",
            mime="text/calendar",
            width="stretch",
            disabled=not selected_events,
        )

    app_module.tool_calendar = tool_calendar_minimal
    app_module._tool3_minimal_installed = True
