"""Add central Google Sheets submission action to Tool 1."""
from __future__ import annotations

import re

from google_sheets_submissions import configured, submit_preferences


_MONTH_FROM_FILENAME = re.compile(r"_(\d{4})_(\d{2})\.xlsx$")


def install(app_module) -> None:
    if getattr(app_module, "_preferences_submission_override_installed", False):
        return

    original = app_module.tool_preferences

    def tool_preferences_with_submission() -> None:
        st = app_module.st
        original_text_input = st.text_input
        original_data_editor = st.data_editor
        original_download_button = st.download_button

        captured = {
            "employee": "",
            "edited": None,
            "submit_rendered": False,
        }

        def capture_text_input(label, *args, **kwargs):
            value = original_text_input(label, *args, **kwargs)
            if kwargs.get("key") == "preferences_employee":
                captured["employee"] = str(value or "")
            return value

        def capture_data_editor(data, *args, **kwargs):
            edited = original_data_editor(data, *args, **kwargs)
            try:
                required = {"תאריך", "חסימה", "חופש", "הערה"}
                if required.issubset(set(edited.columns)):
                    captured["edited"] = edited
            except Exception:
                pass
            return edited

        def submit_then_download(label, *args, **kwargs):
            file_name = str(kwargs.get("file_name", "") or "")
            if file_name.startswith("העדפות_") and not captured["submit_rendered"]:
                captured["submit_rendered"] = True

                match = _MONTH_FROM_FILENAME.search(file_name)
                year = int(match.group(1)) if match else None
                month = int(match.group(2)) if match else None
                employee = str(captured.get("employee") or "").strip()
                edited = captured.get("edited")

                ready = bool(employee and edited is not None and year is not None and month is not None)
                sheets_ready = configured(st)

                if ready:
                    if st.button(
                        "הגש העדפות",
                        type="primary",
                        width="stretch",
                        key=f"submit_preferences_{year}_{month}_{employee}",
                        disabled=not sheets_ready,
                    ):
                        try:
                            values = submit_preferences(st, employee, year, month, edited)
                            st.success(
                                f"ההעדפות של {values[1]} לחודש {values[2]} נקלטו בהצלחה."
                            )
                        except Exception as exc:
                            st.error(f"הגשת ההעדפות נכשלה: {exc}")

                if ready and not sheets_ready:
                    st.caption("הגשה למאגר תופעל לאחר השלמת חיבור Google Sheets של המערכת.")

            return original_download_button(label, *args, **kwargs)

        st.text_input = capture_text_input
        st.data_editor = capture_data_editor
        st.download_button = submit_then_download
        try:
            original()
        finally:
            st.text_input = original_text_input
            st.data_editor = original_data_editor
            st.download_button = original_download_button

    app_module.tool_preferences = tool_preferences_with_submission
    app_module._preferences_submission_override_installed = True
