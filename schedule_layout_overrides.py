"""Robust schedule-layout detection and employee-name filtering for Tool 3."""
from __future__ import annotations

import re

import schedule_parser
from core import normalize_spaces


_HOLIDAY_LABELS = {
    "ראש השנה",
    "ערב ראש השנה",
    "יום כיפור",
    "ערב יום כיפור",
    "סוכות",
    "ערב סוכות",
    "חול המועד סוכות",
    "הושענא רבה",
    "שמיני עצרת",
    "שמחת תורה",
    "שמיני עצרת / שמחת תורה",
    "פסח",
    "ערב פסח",
    "חול המועד פסח",
    "שביעי של פסח",
    "שבועות",
    "ערב שבועות",
    "פורים",
    "תשעה באב",
    "חנוכה",
}


def _fold(value: object) -> str:
    return normalize_spaces(value).casefold()


def _cell_text(sheet, row: int, col: int) -> str:
    if row < 0 or col < 0 or row >= sheet.nrows or col >= sheet.ncols:
        return ""
    return normalize_spaces(sheet.cell(row, col).text)


def _looks_like_holiday_text(value: object) -> bool:
    text = normalize_spaces(value)
    if not text:
        return False
    parts = [normalize_spaces(part) for part in re.split(r"[|,]+", text) if normalize_spaces(part)]
    if not parts:
        parts = [text]
    return any(part in _HOLIDAY_LABELS for part in parts)


def _modern_layout_from_structure(sheet) -> bool:
    """Detect the newer layout even when column C has no recognizable header."""
    # Strong header evidence in the first rows. These are zero-based columns in
    # the newer file: V=21, W=22, X=23.
    expected_headers = {
        21: ("ת. א.יום", "תורנות אשפוז יום", "תורן אשפוז יום"),
        22: ("תורן מיון", "תורנות מיון"),
        23: ("תורן מחלקה", "תורנות מחלקה"),
    }
    for col, terms in expected_headers.items():
        for row in range(min(sheet.nrows, 25)):
            text = _cell_text(sheet, row, col)
            if any(term in text for term in terms):
                return True

    # Column C is the holiday/special-day column in the newer layout. Some
    # source files leave its header blank, but the holiday values themselves
    # are enough to identify the layout safely.
    for row in range(sheet.nrows):
        if _looks_like_holiday_text(_cell_text(sheet, row, 2)):
            return True

    return False


def install(app_module) -> None:
    if getattr(app_module, "_schedule_layout_override_installed", False):
        return

    original_layout_detector = schedule_parser._has_modern_holiday_column
    original_infer_names = app_module.infer_employee_names

    def robust_layout_detector(sheet) -> bool:
        if original_layout_detector(sheet):
            return True

        # Accept additional natural header variants before falling back to
        # structural/content detection.
        for row in range(min(sheet.nrows, 25)):
            text = _cell_text(sheet, row, 2)
            if any(term in text for term in ("חג", "יום מיוחד", "מועד")):
                return True
        return _modern_layout_from_structure(sheet)

    def infer_employee_names_filtered(workbook, config):
        names = list(original_infer_names(workbook, config))
        sheet = workbook.sheet_by_preference(config.get("schedule", {}).get("sheet_names", []))

        holiday_values: set[str] = set()
        if robust_layout_detector(sheet):
            for row in range(sheet.nrows):
                text = _cell_text(sheet, row, 2)
                if not text:
                    continue
                holiday_values.add(_fold(text))
                for part in re.split(r"[|,]+", text):
                    part = normalize_spaces(part)
                    if part:
                        holiday_values.add(part.casefold())

        fixed_holidays = {item.casefold() for item in _HOLIDAY_LABELS}
        return [
            name
            for name in names
            if _fold(name) not in holiday_values and _fold(name) not in fixed_holidays
        ]

    schedule_parser._has_modern_holiday_column = robust_layout_detector
    app_module.infer_employee_names = infer_employee_names_filtered
    app_module._schedule_layout_override_installed = True
