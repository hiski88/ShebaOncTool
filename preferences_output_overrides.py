"""Keep Tool 1 output synchronized and render its final actions in one place."""
from __future__ import annotations

import html
import json
import re
from contextlib import nullcontext

import streamlit.components.v1 as components

from google_sheets_submissions import configured, submit_preferences


VISIBLE_OUTPUT_LABEL = "טקסט להעתקה"
HIDDEN_OUTPUT_LABEL = "קוד לקליטה אוטומטית"
HIDDEN_EXPANDER_LABEL = "קוד מערכת למתכנן - מתקדם"
HIDDEN_CAPTIONS = {
    "זה הפלט שנוח להעתיק ולשלוח, בדומה לכלי של פנימית ד'.",
    "אין צורך לקרוא או לערוך את הקוד. הוא מיועד לקליטה אוטומטית בכלי הריכוז.",
}
HIDDEN_WARNINGS = {
    "יש תאריכים שסומנו גם כחופש וגם כחסימה. המערכת תשמור את שני הסימונים.",
}
_MONTH_FROM_FILENAME = re.compile(r"_(\d{4})_(\d{2})\.xlsx$")


def _render_copy_button(value: str) -> None:
    if not value:
        return

    value_json = json.dumps(value, ensure_ascii=False)
    button_label = html.escape("העתקה")
    components.html(
        f"""
        <div dir="rtl" style="font-family: sans-serif; margin-top: -4px; margin-bottom: 8px;">
          <button id="copy-btn" style="
              width: 100%;
              min-height: 42px;
              border: 1px solid rgba(49, 51, 63, 0.22);
              border-radius: 8px;
              background: white;
              cursor: pointer;
              font-size: 14px;
              font-weight: 600;
          ">{button_label}</button>
        </div>
        <script>
          const textToCopy = {value_json};
          const button = document.getElementById('copy-btn');
          button.addEventListener('click', async () => {{
            let copied = false;
            try {{
              await navigator.clipboard.writeText(textToCopy);
              copied = true;
            }} catch (err) {{
              try {{
                const area = document.createElement('textarea');
                area.value = textToCopy;
                area.style.position = 'fixed';
                area.style.opacity = '0';
                document.body.appendChild(area);
                area.focus();
                area.select();
                copied = document.execCommand('copy');
                document.body.removeChild(area);
              }} catch (fallbackErr) {{}}
            }}
            if (copied) {{
              button.textContent = {json.dumps("הועתק", ensure_ascii=False)};
              setTimeout(() => {{ button.textContent = {json.dumps("העתקה", ensure_ascii=False)}; }}, 1400);
            }}
          }});
        </script>
        """,
        height=58,
    )


def install(app_module) -> None:
    """Render submit, copy, and Excel download exactly once and in that order."""
    if getattr(app_module, "_preferences_output_override_installed", False):
        return

    original = app_module.tool_preferences

    def tool_preferences_with_actions() -> None:
        st = app_module.st
        original_text_area = st.text_area
        original_text_input = st.text_input
        original_data_editor = st.data_editor
        original_expander = st.expander
        original_caption = st.caption
        original_warning = st.warning
        original_download_button = st.download_button

        captured = {
            "visible_output": "",
            "employee": "",
            "edited": None,
            "general_note": "",
            "actions_rendered": False,
        }

        def live_text_area(label, *args, **kwargs):
            if label == HIDDEN_OUTPUT_LABEL:
                if "value" in kwargs:
                    return kwargs["value"]
                if args:
                    return args[0]
                return ""

            if label == VISIBLE_OUTPUT_LABEL:
                value = kwargs.get("value", args[0] if args else "")
                captured["visible_output"] = str(value or "")
                key = kwargs.get("key")
                if key:
                    st.session_state[key] = value
            elif label == "הערה כללית להגשה":
                value = original_text_area(label, *args, **kwargs)
                captured["general_note"] = str(value or "")
                return value
            return original_text_area(label, *args, **kwargs)

        def capture_text_input(label, *args, **kwargs):
            value = original_text_input(label, *args, **kwargs)
            if kwargs.get("key") == "preferences_employee":
                captured["employee"] = str(value or "")
            return value

        def capture_data_editor(data, *args, **kwargs):
            edited = original_data_editor(data, *args, **kwargs)
            try:
                required = {"תאריך", "חופש", "הערה"}
                has_block = "חסימה" in edited.columns or "חסימת תורנות מלאה" in edited.columns
                if required.issubset(set(edited.columns)) and has_block:
                    captured["edited"] = edited
            except Exception:
                pass
            return edited

        def simplified_expander(label, *args, **kwargs):
            if label == HIDDEN_EXPANDER_LABEL:
                return nullcontext()
            return original_expander(label, *args, **kwargs)

        def filtered_caption(body, *args, **kwargs):
            if str(body).strip() in HIDDEN_CAPTIONS:
                return None
            return original_caption(body, *args, **kwargs)

        def filtered_warning(body, *args, **kwargs):
            if str(body).strip() in HIDDEN_WARNINGS:
                return None
            return original_warning(body, *args, **kwargs)

        def ordered_download_button(label, *args, **kwargs):
            file_name = str(kwargs.get("file_name", "") or "")
            is_preferences_download = file_name.startswith("העדפות_")

            if is_preferences_download and not captured["actions_rendered"]:
                captured["actions_rendered"] = True
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
                        key=f"submit_preferences_{year}_{month}",
                        disabled=not sheets_ready,
                    ):
                        try:
                            submission_edited = edited.copy()
                            if "חסימת תורנות מלאה" in submission_edited.columns:
                                submission_edited["חסימה"] = submission_edited["חסימת תורנות מלאה"].fillna(False).astype(bool)
                            values = submit_preferences(st, employee, year, month, submission_edited)
                            display_month = f"{month:02d}-{year:04d}"
                            st.success(
                                f"ההעדפות של {values[1]} לחודש {display_month} נקלטו בהצלחה."
                            )
                        except Exception as exc:
                            st.error(f"הגשת ההעדפות נכשלה: {exc}")

                if ready and not sheets_ready:
                    st.caption("הגשה למאגר תופעל לאחר השלמת חיבור Google Sheets של המערכת.")

                _render_copy_button(captured["visible_output"])

            return original_download_button(label, *args, **kwargs)

        st.text_area = live_text_area
        st.text_input = capture_text_input
        st.data_editor = capture_data_editor
        st.expander = simplified_expander
        st.caption = filtered_caption
        st.warning = filtered_warning
        st.download_button = ordered_download_button
        try:
            original()
        finally:
            st.text_area = original_text_area
            st.text_input = original_text_input
            st.data_editor = original_data_editor
            st.expander = original_expander
            st.caption = original_caption
            st.warning = original_warning
            st.download_button = original_download_button

    app_module.tool_preferences = tool_preferences_with_actions
    app_module._preferences_output_override_installed = True
