"""Oncology-specific compatibility overrides for the first prototype.

The generic parser remains configuration-driven. This module adapts the
existing generated workbook and task summary to the corrected meaning of the
first three operational columns: radiation positions.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Callable

import pandas as pd
from openpyxl import load_workbook

import excel_tools
import schedule_parser


def install() -> None:
    """Install idempotent prototype overrides for radiation columns."""
    _patch_schedule_template()
    _patch_task_summary()


def _patch_schedule_template() -> None:
    current = excel_tools.build_schedule_template
    if getattr(current, "_radiation_columns_override", False):
        return

    original: Callable[..., bytes] = current

    def build_schedule_template(*args: Any, **kwargs: Any) -> bytes:
        raw = original(*args, **kwargs)
        workbook = load_workbook(BytesIO(raw))
        sheet = workbook["סידור עבודה"]
        sheet["D3"] = "קרינה"
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    build_schedule_template._radiation_columns_override = True  # type: ignore[attr-defined]
    excel_tools.build_schedule_template = build_schedule_template


def _patch_task_summary() -> None:
    current = schedule_parser.summarize_schedule
    if getattr(current, "_radiation_columns_override", False):
        return

    original: Callable[[pd.DataFrame], pd.DataFrame] = current

    def summarize_schedule(records: pd.DataFrame) -> pd.DataFrame:
        summary = original(records)
        if summary.empty:
            return summary

        radiation_rows = records[
            (records["record_type"] == "task")
            & (records["task_code"] == "radiation")
        ]
        counts = radiation_rows.groupby("employee").size()
        values = summary["עובד/ת"].map(counts).fillna(0).astype(int)

        if "קרינה" in summary.columns:
            summary["קרינה"] = values
        else:
            position = (
                summary.columns.get_loc("מיון יום")
                if "מיון יום" in summary.columns
                else len(summary.columns)
            )
            summary.insert(position, "קרינה", values)
        return summary

    summarize_schedule._radiation_columns_override = True  # type: ignore[attr-defined]
    schedule_parser.summarize_schedule = summarize_schedule
