"""Tool 3 UX overrides.

The final schedule flow relies on automatic name detection and presents only the
information that is useful to the end user. Technical parsing fields remain in
the backend and downloadable analysis data where appropriate.
"""
from __future__ import annotations


def install(app_module) -> None:
    """Apply automatic-name and simplified-presentation overrides once."""
    if getattr(app_module, "_name_detection_override_installed", False):
        return

    original_tool_calendar = app_module.tool_calendar
    original_summarize_schedule = app_module.summarize_schedule

    def simplified_summary(records):
        summary = original_summarize_schedule(records)
        if summary.empty:
            return summary

        result = summary.copy()

        # Combine two closely related non-clinical activity columns.
        research = result["מחקר"] if "מחקר" in result.columns else 0
        study = result["יום עיון / כנס"] if "יום עיון / כנס" in result.columns else 0
        if "מחקר" in result.columns or "יום עיון / כנס" in result.columns:
            result["מחקר / יום עיון"] = research + study

        # Remove duplicate, technical or low-value summary columns.
        columns_to_drop = [
            "מחלקה סופ\"ש",
            "שיבוצים בסופ\"ש / חג",
            "מטלות בחג / יום מיוחד",
            "כוננויות",
            "מחקר",
            "יום עיון / כנס",
            "אחרי תורנות",
            "סה\"כ מטלות",
        ]
        result = result.drop(columns=[column for column in columns_to_drop if column in result.columns])

        # Use shorter user-facing wording.
        if "תורנות מחלקה רגילה" in result.columns:
            result = result.rename(columns={"תורנות מחלקה רגילה": "תורנות מחלקה"})

        return result

    app_module.summarize_schedule = simplified_summary

    def tool_calendar_automatic_names_only() -> None:
        original_text_area = app_module.st.text_area
        original_warning = app_module.st.warning
        original_dataframe = app_module.st.dataframe
        original_data_editor = app_module.st.data_editor

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

        def simplified_dataframe(data=None, *args, **kwargs):
            # The first Tool 3 table contains raw Excel source text that is
            # useful for debugging but unnecessary for normal users.
            if data is not None and hasattr(data, "columns"):
                columns = set(data.columns)
                if {"תאריך", "יום", "אירוע", "פירוט", "מקור"}.issubset(columns):
                    keep = ["תאריך", "יום", "אירוע"]
                    if data["פירוט"].fillna("").astype(str).str.strip().ne("").any():
                        keep.append("פירוט")
                    data = data[keep]
            return original_dataframe(data, *args, **kwargs)

        def simplified_data_editor(data=None, *args, **kwargs):
            # Calendar selection needs only the action and human-readable
            # event details. Internal task codes and the all-day flag remain
            # in the event objects and are not shown to the user.
            if data is not None and hasattr(data, "columns"):
                columns = set(data.columns)
                if "להוסיף ליומן" in columns and "קוד מטלה" in columns:
                    keep = [
                        column
                        for column in ["להוסיף ליומן", "תאריך", "אירוע", "התחלה", "סיום"]
                        if column in data.columns
                    ]
                    data = data[keep]
                    kwargs["column_order"] = [
                        column
                        for column in ["סיום", "התחלה", "אירוע", "תאריך", "להוסיף ליומן"]
                        if column in keep
                    ]
                    kwargs["disabled"] = [column for column in keep if column != "להוסיף ליומן"]
                    kwargs["column_config"] = {
                        "להוסיף ליומן": app_module.st.column_config.CheckboxColumn("להוסיף ליומן")
                    }
            return original_data_editor(data, *args, **kwargs)

        app_module.st.text_area = text_area_without_name_repair
        app_module.st.warning = clearer_warning
        app_module.st.dataframe = simplified_dataframe
        app_module.st.data_editor = simplified_data_editor
        try:
            original_tool_calendar()
        finally:
            app_module.st.text_area = original_text_area
            app_module.st.warning = original_warning
            app_module.st.dataframe = original_dataframe
            app_module.st.data_editor = original_data_editor

    tool_calendar_automatic_names_only._automatic_names_only = True  # type: ignore[attr-defined]
    app_module.tool_calendar = tool_calendar_automatic_names_only
    app_module._name_detection_override_installed = True
