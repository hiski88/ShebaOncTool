"""Tool 1 MVP preference editor with full/half-duty availability and positive preferences."""
from __future__ import annotations


CONTROL_ROW_LABEL = "כל החודש"


def _simple_output(employee: str, edited, general_note: str) -> str:
    def days_for(column: str) -> list[str]:
        result: list[str] = []
        for _, row in edited.iterrows():
            if str(row.get("יום", "") or "") == CONTROL_ROW_LABEL:
                continue
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
            "מסמנים חופש, חסימות והעדפות לתורנות. אירועי היומן וההערות האישיות נשארים פרטיים ומשמשים לעזר בלבד.",
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
        table["הערה אישית"] = ""
        table["חסימה"] = False

        control_row = {column: "" for column in table.columns}
        control_row["תאריך"] = app_module.pd.NaT
        control_row["יום"] = CONTROL_ROW_LABEL
        control_row["חופש"] = False
        control_row["חסימת תורנות מלאה"] = False
        control_row["חסימת תורנות חצי"] = False
        control_row["מעוניין בתורנות"] = False
        control_row["הערה אישית"] = ""
        control_row["חסימה"] = False
        table = app_module.pd.concat(
            [app_module.pd.DataFrame([control_row]), table],
            ignore_index=True,
        )

        edited = st.data_editor(
            table,
            width="stretch",
            hide_index=True,
            column_order=[
                "הערה אישית",
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
                "הערה אישית": st.column_config.TextColumn(
                    "הערה אישית",
                    width="medium",
                    help="הערה פרטית לתכנון האישי בלבד. אינה נשלחת למתכנן.",
                ),
            },
            key=f"preferences_table_{year}_{month}",
        )

        real_rows = edited[edited["יום"].astype(str) != CONTROL_ROW_LABEL]
        vacation_count = int(real_rows["חופש"].fillna(False).astype(bool).sum())
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
            edited_for_output = real_rows.copy()
            edited_for_output["חסימה"] = edited_for_output["חסימת תורנות מלאה"].fillna(False).astype(bool)
            backend_edited = edited_for_output.rename(columns={"חסימה": "לא זמין"}).copy()
            payload = app_module.build_submission(employee, year, month, backend_edited)
            machine_output = app_module.encode_submission(payload)
            simple_output = _simple_output(employee, edited_for_output, general_note)

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
