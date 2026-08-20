"""Keep tool 1 output synchronized while hiding technical machine output."""
from __future__ import annotations

from contextlib import nullcontext


VISIBLE_OUTPUT_LABEL = "טקסט להעתקה"
HIDDEN_OUTPUT_LABEL = "קוד לקליטה אוטומטית"
HIDDEN_EXPANDER_LABEL = "קוד מערכת למתכנן - מתקדם"


def install(app_module) -> None:
    """Keep the simple output live and remove technical output from the UI."""
    if getattr(app_module, "_preferences_output_override_installed", False):
        return

    original = app_module.tool_preferences

    def tool_preferences_with_live_output() -> None:
        original_text_area = app_module.st.text_area
        original_expander = app_module.st.expander

        def live_text_area(label, *args, **kwargs):
            # The machine payload still gets calculated by the engine, but it is
            # intentionally not shown to end users.
            if label == HIDDEN_OUTPUT_LABEL:
                if "value" in kwargs:
                    return kwargs["value"]
                if args:
                    return args[0]
                return ""

            if label == VISIBLE_OUTPUT_LABEL:
                key = kwargs.get("key")
                if key:
                    if "value" in kwargs:
                        app_module.st.session_state[key] = kwargs["value"]
                    elif args:
                        app_module.st.session_state[key] = args[0]
            return original_text_area(label, *args, **kwargs)

        def simplified_expander(label, *args, **kwargs):
            if label == HIDDEN_EXPANDER_LABEL:
                return nullcontext()
            return original_expander(label, *args, **kwargs)

        app_module.st.text_area = live_text_area
        app_module.st.expander = simplified_expander
        try:
            original()
        finally:
            app_module.st.text_area = original_text_area
            app_module.st.expander = original_expander

    app_module.tool_preferences = tool_preferences_with_live_output
    app_module._preferences_output_override_installed = True
