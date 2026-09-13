"""Private, device-local 12-hour persistence for Tool 1 planning.

The browser localStorage copy is only a persistence backup. During an active
Streamlit session, session_state is the immediate source of truth so reruns
cannot lose edits before localStorage has finished updating.

State is stored per month so switching months cannot overwrite another month's
preferences or carry its general note into the new month.
"""
from __future__ import annotations

import json
import re
import time

try:
    from streamlit_js_eval import streamlit_js_eval
except Exception:
    streamlit_js_eval = None

STATE_KEY = "medstaff_oncology_preferences_private_state_v1"
CALENDAR_EVENTS_KEY = "medstaff_oncology_preferences_calendar_events_v1"
CALENDAR_LABELS_KEY = "medstaff_oncology_loaded_calendar_labels_v1"
TTL_SECONDS = 12 * 60 * 60
RESET_VERSION_KEY = "preferences_private_table_reset_version_v1"
PENDING_BULK_KEY = "preferences_private_pending_bulk_v1"
SESSION_STATE_KEY = "preferences_private_live_state_v1"
EDITOR_SNAPSHOTS_KEY = "preferences_private_editor_snapshots_v1"
CONTROL_ROW_LABEL = "כל החודש"
BULK_COLUMNS = [
    "חופש",
    "חסימת תורנות מלאה",
    "חסימת תורנות חצי",
    "מעוניין בתורנות",
]
_NOTE_KEY_RE = re.compile(r"^preferences_general_note_(\d{4})_(\d{1,2})$")


def _month_key(year: int, month: int) -> str:
    return f"{int(year):04d}-{int(month):02d}"


def _normalize_store(value) -> dict:
    """Normalize current and legacy flat state into the per-month schema."""
    if not isinstance(value, dict):
        return {"employee": "", "months": {}}

    employee = str(value.get("employee", "") or "")
    normalized_months: dict[str, dict] = {}
    months = value.get("months")
    if isinstance(months, dict):
        for key, month_value in months.items():
            if not isinstance(month_value, dict):
                continue
            days = month_value.get("days", {})
            normalized_months[str(key)] = {
                "days": dict(days) if isinstance(days, dict) else {},
                "general_note": str(month_value.get("general_note", "") or ""),
            }
    else:
        # Migrate the previous schema, which held only one selected month.
        try:
            year = int(value.get("year"))
            month = int(value.get("month"))
        except (TypeError, ValueError):
            year = month = 0
        if year and 1 <= month <= 12:
            days = value.get("days", {})
            normalized_months[_month_key(year, month)] = {
                "days": dict(days) if isinstance(days, dict) else {},
                "general_note": str(value.get("general_note", "") or ""),
            }

    return {"employee": employee, "months": normalized_months}


def _read_browser_state():
    if streamlit_js_eval is None:
        return None
    try:
        raw = streamlit_js_eval(
            js_expressions=f"localStorage.getItem('{STATE_KEY}')",
            key="load_preferences_private_state_v2",
        )
        if not raw:
            return None
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        if float(payload.get("expires_at", 0)) <= time.time():
            streamlit_js_eval(
                js_expressions=f"localStorage.removeItem('{STATE_KEY}');",
                key="expire_preferences_private_state_v2",
            )
            return None
        return _normalize_store(payload)
    except Exception:
        return None


def _write_browser_state(payload: dict) -> None:
    if streamlit_js_eval is None:
        return
    try:
        data = _normalize_store(payload)
        data["expires_at"] = time.time() + TTL_SECONDS
        raw = json.dumps(data, ensure_ascii=False)
        streamlit_js_eval(
            js_expressions=f"localStorage.setItem('{STATE_KEY}', {json.dumps(raw)});",
            key="save_preferences_private_state_v2",
        )
    except Exception:
        pass


def _normalize_edited_rows(value) -> dict[int, dict]:
    """Normalize Streamlit data_editor edited_rows keys to integer row numbers."""
    if not isinstance(value, dict):
        return {}
    result: dict[int, dict] = {}
    for row_index, delta in value.items():
        try:
            row_number = int(row_index)
        except (TypeError, ValueError):
            continue
        if isinstance(delta, dict):
            result[row_number] = dict(delta)
    return result


def _changed_cells(previous: dict[int, dict], current: dict[int, dict]) -> list[tuple[int, str, object]]:
    changes: list[tuple[int, str, object]] = []
    rows = set(previous) | set(current)
    for row in rows:
        before = previous.get(row, {})
        after = current.get(row, {})
        columns = set(before) | set(after)
        for column in columns:
            before_has = column in before
            after_has = column in after
            if before_has == after_has and (not before_has or before.get(column) == after.get(column)):
                continue
            if after_has:
                changes.append((row, column, after.get(column)))
    return changes


def _clear_month_widget_state(st, year: int, month: int) -> None:
    prefixes = (
        f"preferences_table_{year}_{month}",
        f"preferences_simple_output_{year}_{month}",
        f"preferences_machine_output_{year}_{month}",
        f"preferences_general_note_{year}_{month}",
        f"preferences_preview_signature_{year}_{month}",
    )
    for key in list(st.session_state.keys()):
        if str(key).startswith(prefixes):
            st.session_state.pop(key, None)


def install(app_module) -> None:
    if getattr(app_module, "_preferences_privacy_override_installed", False):
        return

    original = app_module.tool_preferences

    def private_tool_preferences() -> None:
        st = app_module.st

        browser_saved = _read_browser_state() or {}
        live_saved = st.session_state.get(SESSION_STATE_KEY)
        if not isinstance(live_saved, dict):
            live_saved = browser_saved
        live_saved = _normalize_store(live_saved)
        st.session_state[SESSION_STATE_KEY] = live_saved

        base = getattr(st, "_main", None)
        original_text_input = base.text_input if base is not None else st.text_input
        original_text_area = base.text_area if base is not None else st.text_area
        original_data_editor = base.data_editor if base is not None else st.data_editor

        reset_version = int(st.session_state.get(RESET_VERSION_KEY, 0) or 0)
        captured = {
            "employee": str(live_saved.get("employee", "") or ""),
            "months": {
                key: {
                    "days": dict(value.get("days", {}) or {}),
                    "general_note": str(value.get("general_note", "") or ""),
                }
                for key, value in live_saved.get("months", {}).items()
                if isinstance(value, dict)
            },
        }
        clear_button_rendered = False

        def month_state(year: int, month: int) -> dict:
            key = _month_key(year, month)
            current = captured["months"].get(key)
            if not isinstance(current, dict):
                current = {"days": {}, "general_note": ""}
                captured["months"][key] = current
            if not isinstance(current.get("days"), dict):
                current["days"] = {}
            current["general_note"] = str(current.get("general_note", "") or "")
            return current

        def commit_captured() -> None:
            payload = _normalize_store(captured)
            st.session_state[SESSION_STATE_KEY] = payload
            _write_browser_state(payload)

        def private_text_input(label, *args, **kwargs):
            if kwargs.get("key") == "preferences_employee":
                if "preferences_employee" not in st.session_state and captured["employee"]:
                    kwargs["value"] = captured["employee"]
                value = original_text_input(label, *args, **kwargs)
                captured["employee"] = str(value or "")
                commit_captured()
                return value
            return original_text_input(label, *args, **kwargs)

        def private_text_area(label, *args, **kwargs):
            key = str(kwargs.get("key", ""))
            match = _NOTE_KEY_RE.match(key)
            if match:
                year = int(match.group(1))
                month = int(match.group(2))
                current = month_state(year, month)
                if key not in st.session_state and current["general_note"]:
                    kwargs["value"] = current["general_note"]
                value = original_text_area(label, *args, **kwargs)
                current["general_note"] = str(value or "")
                commit_captured()
                return value
            return original_text_area(label, *args, **kwargs)

        def _rows_to_days(frame) -> dict:
            days = {}
            for _, row in frame.iterrows():
                try:
                    date_key = app_module.pd.Timestamp(row["תאריך"]).date().isoformat()
                except Exception:
                    continue
                vacation = bool(row.get("חופש", False))
                full_block = bool(row.get("חסימת תורנות מלאה", row.get("חסימה", False)))
                half_block = bool(row.get("חסימת תורנות חצי", False))
                wants_duty = bool(row.get("מעוניין בתורנות", False))
                personal_note = str(row.get("הערה אישית", "") or "")
                if vacation or full_block or half_block or wants_duty or personal_note.strip():
                    days[date_key] = {
                        "vacation": vacation,
                        "full_block": full_block,
                        "half_block": half_block,
                        "wants_duty": wants_duty,
                        "personal_note": personal_note,
                    }
            return days

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
                year = month = 0

            current_month = month_state(year, month)
            table = data.copy()
            control_mask = table["יום"].astype(str) == CONTROL_ROW_LABEL if "יום" in table.columns else None
            if control_mask is not None:
                real_mask = ~control_mask
            else:
                real_mask = app_module.pd.Series([True] * len(table), index=table.index)

            saved_days = current_month.get("days", {})
            for idx, row in table[real_mask].iterrows():
                try:
                    date_key = app_module.pd.Timestamp(row["תאריך"]).date().isoformat()
                except Exception:
                    continue
                day = saved_days.get(date_key)
                if not isinstance(day, dict):
                    continue
                table.at[idx, "חופש"] = bool(day.get("vacation", False))
                table.at[idx, "חסימת תורנות מלאה"] = bool(day.get("full_block", day.get("blocked", False)))
                table.at[idx, "חסימת תורנות חצי"] = bool(day.get("half_block", False))
                table.at[idx, "מעוניין בתורנות"] = bool(day.get("wants_duty", False))
                table.at[idx, "הערה אישית"] = str(day.get("personal_note", day.get("note", "")) or "")

            pending_bulk = st.session_state.pop(PENDING_BULK_KEY, None)
            if isinstance(pending_bulk, dict):
                if pending_bulk.get("year") == year and pending_bulk.get("month") == month:
                    column = str(pending_bulk.get("column", ""))
                    if column in BULK_COLUMNS and column in table.columns:
                        table.loc[real_mask, column] = bool(pending_bulk.get("value", False))
                        current_month["days"] = _rows_to_days(table[real_mask])
                        commit_captured()

            if control_mask is not None and bool(control_mask.any()):
                control_index = table.index[control_mask][0]
                for column in BULK_COLUMNS:
                    if column in table.columns:
                        values = table.loc[real_mask, column].fillna(False).astype(bool)
                        table.at[control_index, column] = bool(len(values) and values.all())

            editor_kwargs = dict(kwargs)
            actual_key = f"{source_key}_reset_{reset_version}"
            editor_kwargs["key"] = actual_key

            snapshots = st.session_state.get(EDITOR_SNAPSHOTS_KEY)
            if not isinstance(snapshots, dict):
                snapshots = {}
                st.session_state[EDITOR_SNAPSHOTS_KEY] = snapshots

            def handle_editor_change() -> None:
                state = st.session_state.get(actual_key, {})
                current_rows = _normalize_edited_rows(
                    state.get("edited_rows", {}) if isinstance(state, dict) else {}
                )
                previous_rows = _normalize_edited_rows(snapshots.get(actual_key, {}))
                changes = _changed_cells(previous_rows, current_rows)
                snapshots[actual_key] = current_rows

                for row_number, column, value in changes:
                    if row_number != 0 or column not in BULK_COLUMNS:
                        continue
                    st.session_state[PENDING_BULK_KEY] = {
                        "year": year,
                        "month": month,
                        "column": column,
                        "value": bool(value),
                    }
                    st.session_state[RESET_VERSION_KEY] = reset_version + 1
                    return

            editor_kwargs["on_change"] = handle_editor_change
            edited = original_data_editor(table, *args, **editor_kwargs)

            edited_control_mask = edited["יום"].astype(str) == CONTROL_ROW_LABEL if "יום" in edited.columns else None
            if edited_control_mask is not None:
                edited_real_mask = ~edited_control_mask
            else:
                edited_real_mask = app_module.pd.Series([True] * len(edited), index=edited.index)

            try:
                current_month["days"] = _rows_to_days(edited[edited_real_mask])
            except Exception:
                pass
            commit_captured()

            editor_state = st.session_state.get(actual_key, {})
            current_rows = _normalize_edited_rows(
                editor_state.get("edited_rows", {}) if isinstance(editor_state, dict) else {}
            )
            snapshots[actual_key] = current_rows
            day_columns_changed = {
                column
                for row_number, delta in current_rows.items()
                if row_number != 0
                for column in BULK_COLUMNS
                if column in delta
            }
            if day_columns_changed and edited_control_mask is not None and bool(edited_control_mask.any()):
                control_index = edited.index[edited_control_mask][0]
                visual_needs_refresh = False
                for column in day_columns_changed:
                    values = edited.loc[edited_real_mask, column].fillna(False).astype(bool)
                    derived = bool(len(values) and values.all())
                    displayed = bool(edited.at[control_index, column])
                    if displayed != derived:
                        visual_needs_refresh = True
                        break
                if visual_needs_refresh:
                    st.session_state[RESET_VERSION_KEY] = reset_version + 1
                    st.rerun()

            if not clear_button_rendered:
                clear_button_rendered = True
                if st.button(
                    "נקה את כל הטבלה",
                    width="stretch",
                    key=f"clear_all_preferences_table_{year}_{month}_v13",
                ):
                    captured["months"].pop(_month_key(year, month), None)
                    commit_captured()
                    _clear_month_widget_state(st, year, month)
                    st.session_state.pop(PENDING_BULK_KEY, None)
                    st.session_state.pop(EDITOR_SNAPSHOTS_KEY, None)
                    st.session_state[RESET_VERSION_KEY] = reset_version + 1
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
