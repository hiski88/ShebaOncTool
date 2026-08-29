"""Private, device-local 12-hour persistence for Tool 1 planning.

The planning state is stored only in this browser's localStorage. It is not
written to a shared server-side cache or database. Stored values expire after
12 hours and are scoped to the app origin/browser profile.
"""
from __future__ import annotations

import json
import time

try:
    from streamlit_js_eval import streamlit_js_eval
except Exception:
    streamlit_js_eval = None

STATE_KEY = "medstaff_oncology_preferences_private_state_v1"
CALENDAR_EVENTS_KEY = "medstaff_oncology_preferences_calendar_events_v1"
CALENDAR_LABELS_KEY = "medstaff_oncology_loaded_calendar_labels_v1"
TTL_SECONDS = 12 * 60 * 60
CLEAR_REQUEST_KEY = "preferences_private_clear_all_requested_v1"
RESET_VERSION_KEY = "preferences_private_table_reset_version_v1"
BULK_ACTION_KEY = "preferences_bulk_action_v1"


def _read_browser_state():
    if streamlit_js_eval is None:
        return None
    try:
        raw = streamlit_js_eval(
            js_expressions=f"localStorage.getItem('{STATE_KEY}')",
            key="load_preferences_private_state_v1",
        )
        if not raw:
            return None
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        if float(payload.get("expires_at", 0)) <= time.time():
            streamlit_js_eval(
                js_expressions=f"localStorage.removeItem('{STATE_KEY}');",
                key="expire_preferences_private_state_v1",
            )
            return None
        return payload
    except Exception:
        return None


def _write_browser_state(payload: dict) -> None:
    if streamlit_js_eval is None:
        return
    try:
        data = dict(payload)
        data["expires_at"] = time.time() + TTL_SECONDS
        raw = json.dumps(data, ensure_ascii=False)
        streamlit_js_eval(
            js_expressions=f"localStorage.setItem('{STATE_KEY}', {json.dumps(raw)});",
            key="save_preferences_private_state_v1",
        )
    except Exception:
        pass


def _clear_browser_planning_data() -> None:
    if streamlit_js_eval is None:
        return
    try:
        expression = (
            f"localStorage.removeItem('{STATE_KEY}');"
            f"localStorage.removeItem('{CALENDAR_EVENTS_KEY}');"
            f"localStorage.removeItem('{CALENDAR_LABELS_KEY}');"
        )
        streamlit_js_eval(
            js_expressions=expression,
            key="clear_preferences_private_all_v1",
        )
    except Exception:
        pass


def _clear_session_planning_data(st) -> None:
    st.session_state.pop("preferences_calendar_events", None)
    st.session_state.pop("preferences_loaded_calendar_labels", None)
    st.session_state.pop(BULK_ACTION_KEY, None)
    for key in list(st.session_state.keys()):
        text = str(key)
        if text.startswith("preferences_table_"):
            st.session_state.pop(key, None)
        elif text.startswith("preferences_simple_output_"):
            st.session_state.pop(key, None)
        elif text.startswith("preferences_machine_output_"):
            st.session_state.pop(key, None)
        elif text.startswith("preferences_general_note_"):
            st.session_state.pop(key, None)
        elif text.startswith("preferences_bulk_all_"):
            st.session_state.pop(key, None)


def install(app_module) -> None:
    if getattr(app_module, "_preferences_privacy_override_installed", False):
        return

    original = app_module.tool_preferences

    def private_tool_preferences() -> None:
        st = app_module.st

        cleared_now = bool(st.session_state.pop(CLEAR_REQUEST_KEY, False))
        if cleared_now:
            _clear_session_planning_data(st)
            _clear_browser_planning_data()

        saved = {} if cleared_now else (_read_browser_state() or {})

        base = getattr(st, "_main", None)
        original_text_input = base.text_input if base is not None else st.text_input
        original_text_area = base.text_area if base is not None else st.text_area
        original_data_editor = base.data_editor if base is not None else st.data_editor

        reset_version = int(st.session_state.get(RESET_VERSION_KEY, 0) or 0)
        captured = {
            "employee": str(saved.get("employee", "") or ""),
            "year": saved.get("year"),
            "month": saved.get("month"),
            "days": saved.get("days", {}) if isinstance(saved.get("days", {}), dict) else {},
            "general_note": str(saved.get("general_note", "") or ""),
        }
        clear_button_rendered = False

        def private_text_input(label, *args, **kwargs):
            if kwargs.get("key") == "preferences_employee":
                if "preferences_employee" not in st.session_state and captured["employee"]:
                    kwargs["value"] = captured["employee"]
                value = original_text_input(label, *args, **kwargs)
                captured["employee"] = str(value or "")
                return value
            return original_text_input(label, *args, **kwargs)

        def private_text_area(label, *args, **kwargs):
            key = str(kwargs.get("key", ""))
            if key.startswith("preferences_general_note_"):
                if key not in st.session_state and captured["general_note"]:
                    kwargs["value"] = captured["general_note"]
                value = original_text_area(label, *args, **kwargs)
                captured["general_note"] = str(value or "")
                _write_browser_state(captured)
                return value
            return original_text_area(label, *args, **kwargs)

        def private_data_editor(data, *args, **kwargs):
            nonlocal clear_button_rendered

            source_key = str(kwargs.get("key", ""))
            if not source_key.startswith("preferences_table_"):
                return original_data_editor(data, *args, **kwargs)

            try:
                parts = source_key.rsplit("_", 2)
                year = int(parts[-2])
                month = int(parts[-1])
            except Exception:
                year = month = None

            table = data.copy()
            if year == captured.get("year") and month == captured.get("month"):
                for idx, row in table.iterrows():
                    try:
                        date_key = app_module.pd.Timestamp(row["תאריך"]).date().isoformat()
                    except Exception:
                        continue
                    day = captured["days"].get(date_key)
                    if not isinstance(day, dict):
                        continue
                    table.at[idx, "חופש"] = bool(day.get("vacation", False))
                    table.at[idx, "חסימת תורנות מלאה"] = bool(day.get("full_block", day.get("blocked", False)))
                    table.at[idx, "חסימת תורנות חצי"] = bool(day.get("half_block", False))
                    table.at[idx, "מעוניין בתורנות"] = bool(day.get("wants_duty", False))
                    table.at[idx, "הערה"] = str(day.get("note", "") or "")

            bulk_action = st.session_state.pop(BULK_ACTION_KEY, None)
            if isinstance(bulk_action, dict):
                if bulk_action.get("year") == year and bulk_action.get("month") == month:
                    column = str(bulk_action.get("column", ""))
                    if column in table.columns:
                        table[column] = bool(bulk_action.get("value", False))

            editor_kwargs = dict(kwargs)
            editor_kwargs["key"] = f"{source_key}_reset_{reset_version}"
            edited = original_data_editor(table, *args, **editor_kwargs)

            days = {}
            try:
                for _, row in edited.iterrows():
                    date_key = app_module.pd.Timestamp(row["תאריך"]).date().isoformat()
                    vacation = bool(row.get("חופש", False))
                    full_block = bool(row.get("חסימת תורנות מלאה", row.get("חסימה", False)))
                    half_block = bool(row.get("חסימת תורנות חצי", False))
                    wants_duty = bool(row.get("מעוניין בתורנות", False))
                    note = str(row.get("הערה", "") or "")
                    if vacation or full_block or half_block or wants_duty or note.strip():
                        days[date_key] = {
                            "vacation": vacation,
                            "full_block": full_block,
                            "half_block": half_block,
                            "wants_duty": wants_duty,
                            "note": note,
                        }
            except Exception:
                days = captured.get("days", {})

            captured["year"] = year
            captured["month"] = month
            captured["days"] = days
            _write_browser_state(captured)

            if not clear_button_rendered:
                clear_button_rendered = True
                if st.button(
                    "נקה את כל הטבלה",
                    width="stretch",
                    key=f"clear_all_preferences_table_{year}_{month}_v4",
                ):
                    _clear_browser_planning_data()
                    st.session_state[RESET_VERSION_KEY] = reset_version + 1
                    st.session_state[CLEAR_REQUEST_KEY] = True
                    st.rerun()

            return edited

        st.text_input = private_text_input
        st.text_area = private_text_area
        st.data_editor = private_data_editor
        try:
            original()
        finally:
            st.text_input = original_text_input
            st.text_area = original_text_area
            st.data_editor = original_data_editor

    app_module.tool_preferences = private_tool_preferences
    app_module._preferences_privacy_override_installed = True
