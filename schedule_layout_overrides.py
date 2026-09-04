"""Robust schedule-layout detection and employee-name filtering for Tool 3."""
from __future__ import annotations

import re

import schedule_parser
from core import important_day_name as core_important_day_name, normalize_spaces


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

    for row in range(sheet.nrows):
        if _looks_like_holiday_text(_cell_text(sheet, row, 2)):
            return True

    return False


def _clean_candidate(fragment: str) -> str:
    fragment = fragment.strip(" \t\n,;:|()[]{}")
    return normalize_spaces(fragment)


def _infer_names_from_assignment_columns(workbook, config, modern: bool) -> list[str]:
    """Infer staff only from assignment columns, never from status/absence text."""
    sheet = workbook.sheet_by_preference(config.get("schedule", {}).get("sheet_names", []))
    excluded = {normalize_spaces(term).casefold() for term in config.get("non_name_terms", [])}
    counts: dict[str, int] = {}
    duty_names: set[str] = set()

    rows = schedule_parser.schedule_rows(sheet, config)
    for column in config.get("schedule", {}).get("columns", []):
        if column.get("kind") == "status":
            continue

        col = schedule_parser._effective_column(int(column["index"]), modern)
        if col >= sheet.ncols:
            continue

        for row, _ in rows:
            text = sheet.cell(row, col).text
            if not text:
                continue
            for fragment in re.split(r"[\n,;]+", text):
                candidate = _clean_candidate(fragment)
                folded = candidate.casefold()
                if not candidate or folded in excluded:
                    continue
                if any(term and term in folded for term in excluded):
                    continue
                if any(char.isdigit() for char in candidate):
                    continue
                if "/" in candidate or "+" in candidate:
                    continue
                if len(candidate) < 2 or len(candidate) > 35:
                    continue
                if len(candidate.split()) > 4:
                    continue
                if not re.fullmatch(r"[א-תA-Za-zÀ-ÖØ-öø-ÿ'׳״\- ]+", candidate):
                    continue

                counts[candidate] = counts.get(candidate, 0) + 1
                if column.get("kind") == "duty":
                    duty_names.add(candidate)

    names = [name for name, count in counts.items() if count >= 2 or name in duty_names]
    return sorted(names, key=lambda item: (item.casefold(), item))


def install(app_module) -> None:
    if getattr(app_module, "_schedule_layout_override_installed", False):
        return

    original_layout_detector = schedule_parser._has_modern_holiday_column

    def robust_layout_detector(sheet) -> bool:
        if original_layout_detector(sheet):
            return True

        for row in range(min(sheet.nrows, 25)):
            text = _cell_text(sheet, row, 2)
            if any(term in text for term in ("חג", "יום מיוחד", "מועד")):
                return True
        return _modern_layout_from_structure(sheet)

    def infer_employee_names_filtered(workbook, config):
        sheet = workbook.sheet_by_preference(config.get("schedule", {}).get("sheet_names", []))
        modern = robust_layout_detector(sheet)
        names = _infer_names_from_assignment_columns(workbook, config, modern)

        holiday_values: set[str] = set()
        if modern:
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

    def configured_important_day_name(value, special_days=None):
        merged = dict(app_module.CONFIG.get("special_days", {}) or {})
        if special_days:
            merged.update(dict(special_days))
        return core_important_day_name(value, merged)

    schedule_parser._has_modern_holiday_column = robust_layout_detector
    schedule_parser.infer_employee_names = infer_employee_names_filtered
    schedule_parser.important_day_name = configured_important_day_name
    app_module.infer_employee_names = infer_employee_names_filtered
    app_module._schedule_layout_override_installed = True
