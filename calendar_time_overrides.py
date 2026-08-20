"""Manual duty-time controls for calendar export in tool 3."""
from __future__ import annotations

from datetime import time

import streamlit as st


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

        col_department, col_saturday, col_er, col_day_hospital = st.columns(4)

        with col_department:
            st.markdown("**תורנות מחלקה - א'-ו'**")
            department_start = st.time_input(
                "התחלה",
                value=time(8, 0),
                key="calendar_department_start",
            )
            department_end = st.time_input(
                "סיום ביום למחרת",
                value=time(10, 0),
                key="calendar_department_end",
            )

        with col_saturday:
            st.markdown("**תורנות מחלקה - שבת**")
            saturday_start = st.time_input(
                "התחלה בשבת",
                value=time(9, 0),
                key="calendar_saturday_start",
            )
            saturday_end = st.time_input(
                "סיום ביום ראשון",
                value=time(10, 0),
                key="calendar_saturday_end",
            )

        with col_er:
            st.markdown("**תורנות מיון**")
            er_start = st.time_input(
                "התחלה",
                value=time(16, 0),
                key="calendar_er_start",
            )
            er_end = st.time_input(
                "סיום",
                value=time(21, 0),
                key="calendar_er_end",
            )

        with col_day_hospital:
            st.markdown("**תורנות אשפוז יום**")
            day_hospital_start = st.time_input(
                "התחלה",
                value=time(16, 0),
                key="calendar_day_hospital_start",
            )
            day_hospital_end = st.time_input(
                "סיום",
                value=time(21, 0),
                key="calendar_day_hospital_end",
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

        # The wrapped tool already renders its own header. Suppress only that
        # duplicate header while preserving the rest of its flow unchanged.
        app_module.render_header = lambda *_args, **_kwargs: None
        try:
            original()
        finally:
            app_module.render_header = original_render_header

    tool_calendar_with_times._manual_time_override = True  # type: ignore[attr-defined]
    app_module.tool_calendar = tool_calendar_with_times
