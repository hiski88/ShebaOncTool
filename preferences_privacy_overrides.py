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
TTL_SECONDS = 12 * 60 * 60


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


def install(app_module) -> None:
    if getattr(app_module, "_preferences_privacy_override_installed", False):
        return

    original = app_module.tool_preferences

    def private_tool_preferences() -> None:
        st = app_module.st
        saved = _read_browser_state() or {}
        original_text_input = st.text_input
        original_data_editor = st.data_editor

        captured = {
            "employee": str(saved.get("employee", "") or ""),
            "year": saved.get("year"),
            "month": saved.get("month"),
            "days": saved.get("days", {}) if isinstance(saved.get("days", {}), dict) else {},
        }

        def private_text_input(label, *args, **kwargs):
            if kwargs.get("key") == "preferences_employee":
                if "preferences_employee" not in st.session_state and captured["employee"]:
                    kwargs["value"] = captured["employee"]
                value = original_text_input(label, *args, **kwargs)
                captured["employee"] = str(value or "")
                return value
            return original_text_input(label, *args, **kwargs)

        def private_data_editor(data, *args, **kwargs):
            key = str(kwargs.get("key", ""))
            if not key.startswith("preferences_table_"):
                return original_data_editor(data, *args, **kwargs)

            try:
                parts = key.rsplit("_", 2)
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
                    table.at[idx, "חסימה"] = bool(day.get("blocked", False))
                    table.at[idx, "חופש"] = bool(day.get("vacation", False))
                    table.at[idx, "הערה"] = str(day.get("note", "") or "")

            edited = original_data_editor(table, *args, **kwargs)
            days = {}
            try:
                for _, row in edited.iterrows():
                    date_key = app_module.pd.Timestamp(row["תאריך"]).date().isoformat()
                    blocked = bool(row.get("חסימה", False))
                    vacation = bool(row.get("חופש", False))
                    note = str(row.get("הערה", "") or "")
                    if blocked or vacation or note.strip():
                        days[date_key] = {
                            "blocked": blocked,
                            "vacation": vacation,
                            "note": note,
                        }
            except Exception:
                days = captured.get("days", {})

            captured["year"] = year
            captured["month"] = month
            captured["days"] = days
            _write_browser_state(captured)
            return edited

        st.text_input = private_text_input
        st.data_editor = private_data_editor
        try:
            original()
        finally:
            st.text_input = original_text_input
            st.data_editor = original_data_editor

    app_module.tool_preferences = private_tool_preferences
    app_module._preferences_privacy_override_installed = True
