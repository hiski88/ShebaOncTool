"""Tool 4 reads the latest final schedule stored centrally by Tool 3."""
from __future__ import annotations

from final_schedule_reader import download_final_schedule, latest_final_schedule
from tool3_minimal_overrides import _calendar_candidate_events, _session_calendar_config


IDENTIFIED_WORKER_SESSION_KEY = "medstaff_identified_worker_v1"


def _normalize_name(value: object) -> str:
    return " ".join(str(value or "").strip().split()).casefold()


def _identified_employee_name(st, names: list[str]) -> str | None:
    """Resolve an identified employee to exactly one schedule name.

    Employee mode must never fall back to another person's name. Managers do
    not carry IDENTIFIED_WORKER_SESSION_KEY and therefore keep the normal
    employee selector below.
    """
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


def _default_employee_index(st, names: list[str]) -> int:
    """Backward-compatible manager default; employee mode is resolved separately."""
    resolved = _identified_employee_name(st, names)
    if resolved:
        return names.index(resolved)
    return 0


def install(app_module) -> None:
    """Replace manual Tool 4 upload before calendar-time wrapper captures it."""
    if getattr(app_module, "_tool4_central_schedule_installed", False):
        return

    def tool_calendar_from_central_schedule() -> None:
        st = app_module.st
        app_module.render_header(
            "4. יצירת זימונים ליומן",
            "המערכת קוראת אוטומטית את הגרסה האחרונה של הסידור הסופי שנשמרה על ידי מנהל/ת המערכת.",
        )

        year, month = app_module.month_selector("calendar_final_schedule", offset=0)
        config = _session_calendar_config(app_module, st)

        try:
            schedule_file = latest_final_schedule(st, year, month)
        except Exception as exc:
            st.error(f"לא ניתן לקרוא את ארכיון הסידורים המרכזי: {exc}")
            return

        month_display = f"{month:02d}-{year:04d}"
        if schedule_file is None:
            st.info(
                f"עדיין לא נשמר סידור סופי מרכזי לחודש {month_display}. "
                "לאחר העלאתו בכלי 3 הוא יופיע כאן אוטומטית."
            )
            return

        stored_name = str(schedule_file.get("name", "") or "")
        version = int(schedule_file.get("version", 0) or 0)
        st.success(f"נטען הסידור המרכזי: {stored_name} (גרסה V{version}).")

        try:
            content = download_final_schedule(st, str(schedule_file.get("id", "") or ""))
            workbook = app_module.read_schedule_workbook(content, stored_name)
            names = sorted(set(app_module.infer_employee_names(workbook, config)))
        except Exception as exc:
            st.error(f"לא ניתן לקרוא את הסידור המרכזי: {exc}")
            return

        if not names:
            st.error(
                "לא ניתן לזהות שמות עובדים מהסידור המרכזי באופן אמין. "
                "יש לבדוק בכלי 3 שהועלה קובץ הסידור המקורי במבנה הנתמך."
            )
            return

        identified_worker = st.session_state.get(IDENTIFIED_WORKER_SESSION_KEY)
        if isinstance(identified_worker, dict):
            employee = _identified_employee_name(st, names)
            if not employee:
                st.error(
                    "לא ניתן להתאים באופן אמין את המשתמש/ת המחובר/ת לשם בסידור הסופי. "
                    "מטעמי פרטיות לא יוצגו נתונים של עובדים אחרים. יש לפנות למנהל/ת המערכת."
                )
                return
            st.caption(f"הזימונים מוצגים עבור: {employee}")
        else:
            employee = st.selectbox(
                "בחירת עובד/ת",
                names,
                index=0,
                key=f"calendar_employee_{year}_{month}_{version}",
            )

        try:
            records = app_module.parse_schedule(workbook, config, names)
        except Exception as exc:
            st.error(f"פענוח הסידור המרכזי נכשל: {exc}")
            return

        candidate_records, events, event_config = _calendar_candidate_events(
            app_module,
            records,
            employee,
            config,
        )

        st.subheader("אירועים שזוהו")
        if candidate_records.empty:
            st.info("לא נמצאו תורנויות או אירועים מיוחדים עבור העובד/ת שנבחר/ה.")
        else:
            display_columns = ["date", "day", "task_label", "subtype"]
            display = candidate_records[display_columns].rename(
                columns={"date": "תאריך", "day": "יום", "task_label": "אירוע", "subtype": "פירוט"}
            )
            if (
                "פירוט" in display.columns
                and display["פירוט"].fillna("").astype(str).str.strip().eq("").all()
            ):
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
                key=f"calendar_event_selection_{year}_{month}_{version}_{employee}",
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

    app_module.tool_calendar = tool_calendar_from_central_schedule
    app_module._tool4_central_schedule_installed = True
