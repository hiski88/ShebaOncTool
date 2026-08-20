"""Tool 3 name-detection UX overrides.

The final schedule flow must rely on automatic name detection. End users should
not have to understand or repair the parser by typing missing names manually.
"""
from __future__ import annotations


def install(app_module) -> None:
    """Remove manual name correction from tool 3 and fail clearly on detection errors."""
    original = app_module.tool_calendar
    if getattr(original, "_automatic_names_only", False):
        return

    def tool_calendar_automatic_names_only() -> None:
        original_text_area = app_module.st.text_area
        original_warning = app_module.st.warning

        def text_area_without_name_repair(label, *args, **kwargs):
            if label == "תיקון רשימת שמות, במידת הצורך":
                return ""
            return original_text_area(label, *args, **kwargs)

        def clearer_warning(message, *args, **kwargs):
            if isinstance(message, str) and message.startswith("לא זוהו שמות"):
                app_module.st.error(
                    "לא ניתן לזהות את שמות העובדים מהלוז באופן אמין. "
                    "יש לבדוק שהקובץ הוא קובץ הלוז המקורי ובמבנה הנתמך."
                )
                return None
            return original_warning(message, *args, **kwargs)

        app_module.st.text_area = text_area_without_name_repair
        app_module.st.warning = clearer_warning
        try:
            original()
        finally:
            app_module.st.text_area = original_text_area
            app_module.st.warning = original_warning

    tool_calendar_automatic_names_only._automatic_names_only = True  # type: ignore[attr-defined]
    app_module.tool_calendar = tool_calendar_automatic_names_only
