"""Keep Tool 1 output synchronized while hiding unnecessary helper text."""
from __future__ import annotations

import html
import json
from contextlib import nullcontext

import streamlit.components.v1 as components


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
    """Keep the simple output live and remove technical/help text from the UI."""
    if getattr(app_module, "_preferences_output_override_installed", False):
        return

    original = app_module.tool_preferences

    def tool_preferences_with_live_output() -> None:
        original_text_area = app_module.st.text_area
        original_expander = app_module.st.expander
        original_caption = app_module.st.caption
        original_warning = app_module.st.warning
        original_download_button = app_module.st.download_button
        visible_output = {"value": ""}
        copy_rendered = {"value": False}

        def live_text_area(label, *args, **kwargs):
            if label == HIDDEN_OUTPUT_LABEL:
                if "value" in kwargs:
                    return kwargs["value"]
                if args:
                    return args[0]
                return ""

            if label == VISIBLE_OUTPUT_LABEL:
                value = kwargs.get("value", args[0] if args else "")
                visible_output["value"] = str(value or "")
                key = kwargs.get("key")
                if key:
                    app_module.st.session_state[key] = value
            return original_text_area(label, *args, **kwargs)

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
            if file_name.startswith("העדפות_") and not copy_rendered["value"]:
                _render_copy_button(visible_output["value"])
                copy_rendered["value"] = True
            return original_download_button(label, *args, **kwargs)

        app_module.st.text_area = live_text_area
        app_module.st.expander = simplified_expander
        app_module.st.caption = filtered_caption
        app_module.st.warning = filtered_warning
        app_module.st.download_button = ordered_download_button
        try:
            original()
        finally:
            app_module.st.text_area = original_text_area
            app_module.st.expander = original_expander
            app_module.st.caption = original_caption
            app_module.st.warning = original_warning
            app_module.st.download_button = original_download_button

    app_module.tool_preferences = tool_preferences_with_live_output
    app_module._preferences_output_override_installed = True
