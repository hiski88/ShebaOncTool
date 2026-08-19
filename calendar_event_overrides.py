"""Calendar-event compatibility overrides for selectable employee statuses."""
from __future__ import annotations

from typing import Any, Callable, Mapping

import pandas as pd

import core


def install() -> None:
    current = core.records_to_events
    if getattr(current, "_status_calendar_override", False):
        return

    original: Callable[[pd.DataFrame, str, Mapping[str, Any]], list] = current

    def records_to_events(records: pd.DataFrame, employee: str, config: Mapping[str, Any]):
        if records.empty or "record_type" not in records.columns:
            return original(records, employee, config)

        prepared = records.copy()
        defaults = config.get("event_defaults", {})
        status_mask = prepared["record_type"].eq("status")
        create_mask = prepared["task_code"].map(
            lambda code: bool(defaults.get(str(code), {}).get("create", False))
        )
        prepared.loc[status_mask & create_mask, "record_type"] = "task"
        return original(prepared, employee, config)

    records_to_events._status_calendar_override = True  # type: ignore[attr-defined]
    core.records_to_events = records_to_events
