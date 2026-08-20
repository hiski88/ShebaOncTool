"""Manual duty-time controls for calendar export in tool 3."""
from __future__ import annotations

import streamlit as st


TIME_OPTIONS = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 15, 30, 45)]


def _time_selector(label: str, default: str, key: str) -> str:
    """Render a stable HH:MM selector that is not affected by browser RTL time controls."""
    try:
        index = TIME_OPTIONS.index(default)
    except ValueError:
        index = 0
    return st.selectbox(
        label,
        TIME_OPTIONS,
        index=index,
        key=key,
        format_func=lambda value: f"\u200e{value}\u200e",
    )


def _time_card(
    title: str,
    start_label: str,
    end_label: str,
    start_value: str,
    end_value: str,
    start_key: str,
    end_key: str,
):
    with st.container(border=True):
        st.markdown(f"### {title}")
        start_col, end_col = st.columns(2)
        with start_col:
            start_time = _time_selector(start_label, start_value, start_key)
        with end_col:
            end_time = _time_selector(end_label, end_value, end_key)
    return start_time, end_time


def install(app_module) -> None:
    """Wrap tool 3 once per app module, even across Streamlit reruns."""
    if getattr(app_module, "_calendar_time_override_installed", False):
        return

    original = app_module.tool_calendar
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
                "08:00",
                "10:00",
                "calendar_department_start_v2",
                "calendar_department_end_v2",
            )
        with row1_left:
            saturday_start, saturday_end = _time_card(
                "תורנות מחלקה - שבת",
                "התחלה בשבת",
                "סיום ביום ראשון",
                "09:00",
                "10:00",
                "calendar_saturday_start_v2",
                "calendar_saturday_end_v2",
            )

        row2_left, row2_right = st.columns(2, gap="medium")
        with row2_right:
            er_start, er_end = _time_card(
                "תורנות מיון",
                "התחלה",
                "סיום",
                "16:00",
                "21:00",
                "calendar_er_start_v2",
                "calendar_er_end_v2",
            )
        with row2_left:
            day_hospital_start, day_hospital_end = _time_card(
                "תורנות אשפוז יום",
                "התחלה",
                "סיום",
                "16:00",
                "21:00",
                "calendar_day_hospital_start_v2",
                "calendar_day_hospital_end_v2",
            )

        defaults = app_module.CONFIG.setdefault("event_defaults", {})

        for code in ("ward_duty_regular", "ward_duty_friday"):
            settings = defaults.setdefault(code, {})
            settings.update({
                "all_day": False,
                "start": department_start,
                "end": department_end,
                "end_day_offset": 1,
                "create": True,
            })

        defaults.setdefault("ward_duty_saturday", {}).update({
            "all_day": False,
            "start": saturday_start,
            "end": saturday_end,
            "end_day_offset": 1,
            "create": True,
        })
        defaults.setdefault("er_duty", {}).update({
            "all_day": False,
            "start": er_start,
            "end": er_end,
            "end_day_offset": 0,
            "create": True,
        })
        defaults.setdefault("day_hospital_duty", {}).update({
            "all_day": False,
            "start": day_hospital_start,
            "end": day_hospital_end,
            "end_day_offset": 0,
            "create": True,
        })

        st.divider()

        app_module.render_header = lambda *_args, **_kwargs: None
        try:
            original()
        finally:
            app_module.render_header = original_render_header

    tool_calendar_with_times._manual_time_override = True  # type: ignore[attr-defined]
    app_module.tool_calendar = tool_calendar_with_times
    app_module._calendar_time_override_installed = True
