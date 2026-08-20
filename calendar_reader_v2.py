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
LOADED_CALENDARS_KEY = "medstaff_oncology_loaded_calendar_labels_v1"


def _load_json(key: str, default):
    if streamlit_js_eval is None:
        return default
    try:
        raw = streamlit_js_eval(
            js_expressions=f"localStorage.getItem('{key}')",
            key=f"load_{key}",
        )
        if not raw:
            return default
        value = json.loads(raw)
        return value
    except Exception:
        return default


def _save_json(key: str, value) -> None:
    if streamlit_js_eval is None:
        return
    try:
        payload = json.dumps(value, ensure_ascii=False)
        streamlit_js_eval(
            js_expressions=f"localStorage.setItem('{key}', {json.dumps(payload)});",
            key=f"save_{key}",
        )
    except Exception:
        pass


def _remove_local(key: str) -> None:
    if streamlit_js_eval is None:
        return
    try:
        streamlit_js_eval(
            js_expressions=f"localStorage.removeItem('{key}');",
            key=f"clear_{key}",
        )
    except Exception:
        pass


def _load_local_events() -> dict[str, list[str]]:
    payload = _load_json(LOCAL_STORAGE_KEY, {})
    if not isinstance(payload, dict):
        return {}
    return {
        str(day): [str(item) for item in items]
        for day, items in payload.items()
        if isinstance(items, list)
    }


def _load_local_calendar_labels() -> list[str]:
    payload = _load_json(LOADED_CALENDARS_KEY, [])
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload]


def _merge(existing: dict[str, list[str]], new: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for key in set(existing) | set(new):
        merged[key] = list(dict.fromkeys([*existing.get(key, []), *new.get(key, [])]))
    return merged


def render_calendar_reader(year: int, month: int, config: dict) -> dict[str, list[str]]:
    st.subheader("אירועים מהיומנים האישיים")
    st.caption("טוענים יומן אחד, ואם צריך מוסיפים יומן שני. האירועים מצטברים ואינם מסמנים חסימה אוטומטית.")

    if "preferences_calendar_events" not in st.session_state:
        st.session_state["preferences_calendar_events"] = _load_local_events()
    elif not st.session_state["preferences_calendar_events"]:
        browser_events = _load_local_events()
        if browser_events:
            st.session_state["preferences_calendar_events"] = browser_events

    if "preferences_loaded_calendar_labels" not in st.session_state:
        st.session_state["preferences_loaded_calendar_labels"] = _load_local_calendar_labels()

    events_by_date = st.session_state.get("preferences_calendar_events", {})
    loaded_labels = st.session_state.get("preferences_loaded_calendar_labels", [])

    if events_by_date:
        loaded_text = ", ".join(loaded_labels[:2]) if loaded_labels else "היומנים שנטענו"
        st.success(f"נשמרו אירועים מ-{loaded_text}. ניתן להוסיף יומן נוסף בלי למחוק אותם.")

    if not oauth_dependencies_available():
        st.info("חיבור היומן אינו זמין כרגע בסביבת האפליקציה.")
        return events_by_date
    if not oauth_configured(st):
        st.info("נדרשת הגדרה חד-פעמית של חיבור Google Calendar ב-Streamlit כדי לאפשר טעינת יומנים.")
        return events_by_date

    credentials = get_credentials(st)
    if credentials is None:
        st.link_button("התחברות ל-Google Calendar", authorization_url(st), width="stretch")
        st.caption("החיבור הוא לקריאה בלבד. אירועים שכבר נטענו נשמרים במכשיר זה.")
        return events_by_date

    try:
        service = build_service(credentials)
        calendars = list_readable_calendars(service)
    except Exception as exc:
        st.warning(f"לא ניתן לקרוא את רשימת היומנים: {exc}")
        return events_by_date

    options = {item["label"]: item for item in calendars}
    labels = list(options)
    if not labels:
        st.warning("לא נמצאו יומנים זמינים בחשבון Google המחובר.")
        return events_by_date

    selected_label = st.selectbox(
        "בחירת יומן לטעינה",
        labels,
        key="preferences_calendar_single_selection_v3",
    )

    already_loaded = selected_label in loaded_labels
    if already_loaded:
        st.caption("יומן זה כבר נטען. טעינה נוספת רק תשלים אירועים חסרים ולא תיצור כפילויות.")
    elif len(loaded_labels) >= 2:
        st.warning("כבר נטענו שני יומנים. כדי לבחור אחרים יש לנקות את האירועים ולהתחיל מחדש.")

    col_load, col_clear, col_disconnect = st.columns([2, 1, 1])
    with col_load:
        if st.button(
            "טען את היומן",
            type="primary",
            width="stretch",
            key="load_preferences_calendar_v3",
            disabled=(len(loaded_labels) >= 2 and not already_loaded),
        ):
            try:
                loaded = read_calendar_events(
                    service,
                    [options[selected_label]],
                    year,
                    month,
                    config.get("timezone", "Asia/Jerusalem"),
                )
                merged = _merge(events_by_date, loaded)
                st.session_state["preferences_calendar_events"] = merged
                if selected_label not in loaded_labels:
                    loaded_labels = [*loaded_labels, selected_label][:2]
                    st.session_state["preferences_loaded_calendar_labels"] = loaded_labels
                _save_json(LOCAL_STORAGE_KEY, merged)
                _save_json(LOADED_CALENDARS_KEY, loaded_labels)
                events_by_date = merged
                if len(loaded_labels) == 1:
                    st.success("היומן נטען. ניתן עכשיו לבחור יומן נוסף ולטעון גם אותו.")
                else:
                    st.success("היומן נוסף. האירועים משני היומנים מוצגים יחד.")
            except Exception as exc:
                st.error(f"טעינת אירועי היומן נכשלה: {exc}")

    with col_clear:
        if st.button("נקה אירועים", width="stretch", key="clear_preferences_calendars_v3"):
            st.session_state["preferences_calendar_events"] = {}
            st.session_state["preferences_loaded_calendar_labels"] = []
            _remove_local(LOCAL_STORAGE_KEY)
            _remove_local(LOADED_CALENDARS_KEY)
            events_by_date = {}
            st.success("אירועי היומנים נוקו מהמכשיר הזה.")

    with col_disconnect:
        if st.button("נתק Google", width="stretch", key="disconnect_preferences_calendar_v3"):
            _save_json(LOCAL_STORAGE_KEY, events_by_date)
            _save_json(LOADED_CALENDARS_KEY, loaded_labels)
            disconnect(st)
            st.info("החיבור נותק. האירועים שכבר נטענו נשארו שמורים במכשיר.")

    return events_by_date
