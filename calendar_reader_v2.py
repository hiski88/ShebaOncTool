from __future__ import annotations

import json

import streamlit as st

from google_calendar import (
    authorization_url,
    build_service,
    disconnect,
    get_credentials,
    list_readable_calendars,
    oauth_configured,
    oauth_dependencies_available,
    read_calendar_events,
)

try:
    from streamlit_js_eval import streamlit_js_eval
except Exception:
    streamlit_js_eval = None

LOCAL_STORAGE_KEY = "medstaff_oncology_preferences_calendar_events_v1"


def _load_local_events() -> dict[str, list[str]]:
    if streamlit_js_eval is None:
        return {}
    try:
        raw = streamlit_js_eval(
            js_expressions=f"localStorage.getItem('{LOCAL_STORAGE_KEY}')",
            key="load_oncology_calendar_events_local_storage",
        )
        if not raw:
            return {}
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return {}
        return {
            str(day): [str(item) for item in items]
            for day, items in payload.items()
            if isinstance(items, list)
        }
    except Exception:
        return {}


def _save_local_events(events: dict[str, list[str]]) -> None:
    if streamlit_js_eval is None:
        return
    try:
        payload = json.dumps(events, ensure_ascii=False)
        streamlit_js_eval(
            js_expressions=f"localStorage.setItem('{LOCAL_STORAGE_KEY}', {json.dumps(payload)});",
            key="save_oncology_calendar_events_local_storage",
        )
    except Exception:
        pass


def _clear_local_events() -> None:
    if streamlit_js_eval is None:
        return
    try:
        streamlit_js_eval(
            js_expressions=f"localStorage.removeItem('{LOCAL_STORAGE_KEY}');",
            key="clear_oncology_calendar_events_local_storage",
        )
    except Exception:
        pass


def _merge(existing: dict[str, list[str]], new: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for key in set(existing) | set(new):
        merged[key] = list(dict.fromkeys([*existing.get(key, []), *new.get(key, [])]))
    return merged


def render_calendar_reader(year: int, month: int, config: dict) -> dict[str, list[str]]:
    st.subheader("אירועים מהיומנים האישיים")
    st.caption("אפשר לטעון עד שני יומנים. האירועים מוצגים לעזר בלבד ואינם מסמנים חסימה אוטומטית.")

    if "preferences_calendar_events" not in st.session_state:
        st.session_state["preferences_calendar_events"] = _load_local_events()
    elif not st.session_state["preferences_calendar_events"]:
        browser_events = _load_local_events()
        if browser_events:
            st.session_state["preferences_calendar_events"] = browser_events

    events_by_date = st.session_state.get("preferences_calendar_events", {})

    if events_by_date:
        st.success("אירועי יומן שכבר נטענו נשמרים במכשיר זה ומוצגים גם לאחר רענון.")

    if not oauth_dependencies_available():
        st.info("חיבור Google Calendar אינו זמין כרגע. ניתן להמשיך לתכנן ידנית.")
        return events_by_date
    if not oauth_configured(st):
        st.info("חיבור Google Calendar טרם הוגדר באפליקציה. ניתן להמשיך לתכנן ידנית.")
        return events_by_date

    credentials = get_credentials(st)
    if credentials is None:
        st.link_button("התחברות ל-Google Calendar", authorization_url(st), width="stretch")
        return events_by_date

    try:
        service = build_service(credentials)
        calendars = list_readable_calendars(service)
    except Exception as exc:
        st.warning(f"לא ניתן לקרוא את רשימת היומנים: {exc}")
        return events_by_date

    options = {item["label"]: item for item in calendars}
    labels = list(options)
    selected_labels = st.multiselect(
        "בחירת יומנים להצגה",
        labels,
        max_selections=2,
        help="ניתן לבחור יומן אחד או שניים. טעינה נוספת מצטרפת לאירועים שכבר נטענו.",
        key="preferences_calendar_selection_v2",
    )

    st.caption("בחר יומן אחד או שניים ולחץ על טעינה. ניתן לחזור בהמשך ולצרף יומן נוסף בלי למחוק את האירועים שכבר נטענו.")

    col_load, col_clear, col_disconnect = st.columns([2, 1, 1])
    with col_load:
        if st.button("טען אירועים מהיומנים", type="primary", width="stretch", key="load_preferences_calendars_v2"):
            if not selected_labels:
                st.warning("יש לבחור לפחות יומן אחד.")
            else:
                selected = [options[label] for label in selected_labels]
                try:
                    loaded = read_calendar_events(
                        service,
                        selected,
                        year,
                        month,
                        config.get("timezone", "Asia/Jerusalem"),
                    )
                    merged = _merge(events_by_date, loaded)
                    st.session_state["preferences_calendar_events"] = merged
                    _save_local_events(merged)
                    events_by_date = merged
                    st.success("אירועי היומן נטענו ונשמרו במכשיר זה.")
                except Exception as exc:
                    st.error(f"טעינת אירועי היומן נכשלה: {exc}")
    with col_clear:
        if st.button("נקה אירועים", width="stretch", key="clear_preferences_calendars_v2"):
            st.session_state["preferences_calendar_events"] = {}
            _clear_local_events()
            events_by_date = {}
            st.success("אירועי היומן נוקו מהמכשיר הזה.")
    with col_disconnect:
        if st.button("נתק יומן", width="stretch", key="disconnect_preferences_calendar_v2"):
            _save_local_events(events_by_date)
            disconnect(st)
            st.info("החיבור נותק. האירועים שכבר נטענו נשמרו במכשיר ולא נמחקו.")

    return events_by_date
