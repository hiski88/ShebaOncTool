"""Keep tool 1 generated outputs synchronized with the edited preference table."""
from __future__ import annotations


OUTPUT_LABELS = {"טקסט להעתקה", "קוד לקליטה אוטומטית"}


def install(app_module) -> None:
    """Ensure generated text areas refresh whenever their computed value changes."""
    if getattr(app_module, "_preferences_output_override_installed", False):
        return

    original = app_module.tool_preferences

    def tool_preferences_with_live_output() -> None:
        original_text_area = app_module.st.text_area

        def live_text_area(label, *args, **kwargs):
            if label in OUTPUT_LABELS:
                key = kwargs.get("key")
                if key:
                    if "value" in kwargs:
                        app_module.st.session_state[key] = kwargs["value"]
                    elif args:
                        app_module.st.session_state[key] = args[0]
            return original_text_area(label, *args, **kwargs)

        app_module.st.text_area = live_text_area
        try:
            original()
        finally:
            app_module.st.text_area = original_text_area

    app_module.tool_preferences = tool_preferences_with_live_output
    app_module._preferences_output_override_installed = True
