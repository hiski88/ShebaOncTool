"""Tool 1 MVP preference editor with full/half-duty availability and positive preferences."""
from __future__ import annotations


BULK_ACTION_KEY = "preferences_bulk_action_v1"
RESET_VERSION_KEY = "preferences_private_table_reset_version_v1"


COLUMNS = [
    ("חופש", "חופש"),
    ("חסימת תורנות מלאה", "חסימת תורנות מלאה"),
    ("חסימת תורנות חצי", "חסימת תורנות חצי"),
    ("מעוניין בתורנות", "מעוניין בתורנות"),
]


def _simple_output(employee: str, edited, general_note: str) -> str:
    def days_for(column: str) -> list[str]:
        result: list[str] = []
        for _, row in edited.iterrows():
            if bool(row.get(column, False)):
                try:
                    result.append(str(int(row["תאריך"].day)))
                except Exception:
                    continue
        return result

    lines = [
        employee.strip(),
        f"חופשים- {','.join(days_for('חופש'))}",
        f"חסימת תורנות מלאה- {','.join(days_for('חסימת תורנות מלאה'))}",
        f"חסימת תורנות חצי- {','.join(days_for('חסימת תורנות חצי'))}",
        f"מעוניין בתורנות- {','.join(days_for('מעוניין בתורנות'))}",
    ]
    note = str(general_note or "").strip()
    if note:
        lines.append(f"הערה כללית- {note}")
    return "\n".join(lines)


def install(app_module) -> None:
    if getattr(app_module, "_tool1_preferences_mvp_override_installed", False):
        return

    def tool_preferences_mvp() -> None:
        st = app_module.st
        app_module.render_header(
            "1. תכנון העדפות אישיות",
            "מסמנים חופש, חסימות והעדפות לתורנות. אירועי היומן נשארים פרטיים ומשמשים לעזר בלבד.",
        )
        year, month = app_module.month_selector("preferences", offset=1)
        employee = st.text_input("שם עובד/ת", placeholder="שם מלא", key="preferences_employee")

        events_by_date = app_module.render_calendar_reader(year, month)

        table = app_module.build_month_table(year, month)
        table["אירועים מהיומן"] = table["תאריך"].map(
            lambda value: "\n".join(events_by_date.get(app_module.pd.Timestamp(value).date().isoformat(), []))
        )
        table["חופש"] = False
        table["חסימת תורנות מלאה"] = False
        table["חסימת תורנות חצי"] = False
        table["מעוניין בתורנות"] = False
        table["הערה"] = ""
        # Compatibility field for the current submission backend. It is hidden
        # from the user and mirrors full-duty blocking after editing.
        table["חסימה"] = False

        st.caption("פעולות מהירות לכל החודש")
        action_cols = st.columns(4)
        for index, (column, label) in enumerate(COLUMNS):
            state_key = f"preferences_bulk_all_{year}_{month}_{column}"
            is_all = bool(st.session_state.get(state_key, False))
            button_label = f"נקה הכל - {label}" if is_all else f"סמן הכל - {label}"
            with action_cols[index]:
                if st.button(button_label, width="stretch", key=f"bulk_{year}_{month}_{index}"):
                    target = not is_all
                    st.session_state[state_key] = target
                    st.session_state[BULK_ACTION_KEY] = {
                        "year": year,
                        "month": month,
                        "column": column,
                        "value": target,
                    }
                    st.session_state[RESET_VERSION_KEY] = int(st.session_state.get(RESET_VERSION_KEY, 0) or 0) + 1
                    st.rerun()

        edited = st.data_editor(
            table,
            width="stretch",
            hide_index=True,
            column_order=[
                "הערה",
                "מעוניין בתורנות",
                "חסימת תורנות חצי",
                "חסימת תורנות מלאה",
                "חופש",
                "אירועים מהיומן",
                "חג / יום מיוחד",
                "יום",
                "תאריך",
            ],
            disabled=["תאריך", "יום", "חג / יום מיוחד", "אירועים מהיומן"],
            column_config={
                "תאריך": st.column_config.DateColumn("תאריך", format="DD.MM.YYYY"),
                "יום": st.column_config.TextColumn("יום"),
                "חג / יום מיוחד": st.column_config.TextColumn("חג / יום מיוחד"),
                "אירועים מהיומן": st.column_config.TextColumn("אירועים מהיומן", width="large"),
                "חופש": st.column_config.CheckboxColumn("חופש"),
                "חסימת תורנות מלאה": st.column_config.CheckboxColumn("חסימת תורנות מלאה"),
                "חסימת תורנות חצי": st.column_config.CheckboxColumn("חסימת תורנות חצי"),
                "מעוניין בתורנות": st.column_config.CheckboxColumn("מעוניין בתורנות"),
                "הערה": st.column_config.TextColumn("הערה", width="medium"),
            },
            key=f"preferences_table_{year}_{month}",
        )

        # Vacation has precedence over every other availability/preference flag.
        # We intentionally do not erase the other values, so cancelling vacation
        # restores the user's previous choices without data loss.
        vacation_count = int(edited["חופש"].fillna(False).astype(bool).sum())
        if vacation_count:
            st.caption("חופש גובר על כל סימון אחר באותו יום. סימונים אחרים נשמרים ולא נמחקים.")

        general_note = st.text_area(
            "הערה כללית להגשה",
            placeholder="למשל: עדיפות לתורנויות בתחילת החודש, מילואים, או בקשה כללית אחרת",
            key=f"preferences_general_note_{year}_{month}",
            height=90,
        )

        if not employee.strip():
            st.info("לאחר הזנת שם, הפלט יופק אוטומטית.")
            return

        try:
            # Keep current backend/export compatibility until Tool 2 storage is
            # upgraded in the next phase.
            edited = edited.copy()
            edited["חסימה"] = edited["חסימת תורנות מלאה"].fillna(False).astype(bool)
            backend_edited = edited.rename(columns={"חסימה": "לא זמין"}).copy()
            payload = app_module.build_submission(employee, year, month, backend_edited)
            machine_output = app_module.encode_submission(payload)
            simple_output = _simple_output(employee, edited, general_note)

            st.subheader("פלט פשוט להעברה")
            st.text_area(
                "טקסט להעתקה",
                value=simple_output,
                height=165,
                key=f"preferences_simple_output_{year}_{month}_{employee}",
            )

            with st.expander("קוד מערכת למתכנן - מתקדם"):
                st.text_area(
                    "קוד לקליטה אוטומטית",
                    value=machine_output,
                    height=180,
                    key=f"preferences_machine_output_{year}_{month}_{employee}",
                )

            workbook = app_module.build_personal_submission_workbook(employee, backend_edited, machine_output)
            st.download_button(
                "הורדת ההעדפות כקובץ Excel",
                data=workbook,
                file_name=f"העדפות_{employee}_{year}_{month:02d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        except Exception as exc:
            st.error(str(exc))

    app_module.tool_preferences = tool_preferences_mvp
    app_module._tool1_preferences_mvp_override_installed = True
