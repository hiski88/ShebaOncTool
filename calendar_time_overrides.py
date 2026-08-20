"""Manual duty-time controls for calendar export in tool 3."""
from __future__ import annotations

from datetime import time

import streamlit as st


def _time_card(title: str, start_label: str, end_label: str, start_value: time, end_value: time, start_key: str, end_key: str):
    with st.container(border=True):
        st.markdown(f"### {title}")
        start_col, end_col = st.columns(2)
        with start_col:
            start_time = st.time_input(start_label, value=start_value, key=start_key)
        with end_col:
            end_time = st.time_input(end_label, value=end_value, key=end_key)
    return start_time, end_time


def install(app_module) -> None:
    """Wrap tool 3 with editable duty times before calendar export."""
    original = app_module.tool_calendar
    if getattr(original, "_manual_time_override", False):
        return

    original_render_header = app_module.render_header

    def tool_calendar_with_times() -> None:
        original_render_header(
            "3. לוז סופי ושמירה ביומן",
            "שומרים ביומן רק תורנויות ואירועים מיוחדים. לפני יצירת ICS ניתן להתאים את שעות התורנויות.",
        )

        st.subheader("שעות תורנות")
        st.caption(
            "השעות משמשות בעיקר להצגה מסודרת ביומן. אלו ערכי ברירת מחדל בלבד וניתן לשנות אותם לפני יצירת ICS או כתיבה ליומן Google."
        )

        row1_left, row1_right = st.columns(2, gap="medium")
        with row1_right:
            department_start, department_end = _time_card(
                "תורנות מחלקה - א'-ו'",
                "התחלה",
                "סיום ביום למחרת",
                time(8, 0),
                time(10, 0),
                "calendar_department_start",
                "calendar_department_end",
            )
        with row1_left:
            saturday_start, saturday_end = _time_card(
                "תורנות מחלקה - שבת",
                "התחלה בשבת",
                "סיום ביום ראשון",
                time(9, 0),
                time(10, 0),
                "calendar_saturday_start",
                "calendar_saturday_end",
            )

        row2_left, row2_right = st.columns(2, gap="medium")
        with row2_right:
            er_start, er_end = _time_card(
                "תורנות מיון",
                "התחלה",
                "סיום",
                time(16, 0),
                time(21, 0),
                "calendar_er_start",
                "calendar_er_end",
            )
        with row2_left:
            day_hospital_start, day_hospital_end = _time_card(
                "תורנות אשפוז יום",
                "התחלה",
                "סיום",
                time(16, 0),
                time(21, 0),
                "calendar_day_hospital_start",
                "calendar_day_hospital_end",
            )

        defaults = app_module.CONFIG.setdefault("event_defaults", {})

        for code in ("ward_duty_regular", "ward_duty_friday"):
            settings = defaults.setdefault(code, {})
            settings.update(
                {
                    "all_day": False,
                    "start": department_start.strftime("%H:%M"),
                    "end": department_end.strftime("%H:%M"),
                    "end_day_offset": 1,
                    "create": True,
                }
            )

        saturday_settings = defaults.setdefault("ward_duty_saturday", {})
        saturday_settings.update(
            {
                "all_day": False,
                "start": saturday_start.strftime("%H:%M"),
                "end": saturday_end.strftime("%H:%M"),
                "end_day_offset": 1,
                "create": True,
            }
        )

        er_settings = defaults.setdefault("er_duty", {})
        er_settings.update(
            {
                "all_day": False,
                "start": er_start.strftime("%H:%M"),
                "end": er_end.strftime("%H:%M"),
                "end_day_offset": 0,
                "create": True,
            }
        )

        day_hospital_settings = defaults.setdefault("day_hospital_duty", {})
        day_hospital_settings.update(
            {
                "all_day": False,
                "start": day_hospital_start.strftime("%H:%M"),
                "end": day_hospital_end.strftime("%H:%M"),
                "end_day_offset": 0,
                "create": True,
            }
        )

        st.divider()

        app_module.render_header = lambda *_args, **_kwargs: None
        try:
            original()
        finally:
            app_module.render_header = original_render_header

    tool_calendar_with_times._manual_time_override = True  # type: ignore[attr-defined]
    app_module.tool_calendar = tool_calendar_with_times
