"""Protect Tool 6 against accidental duplicate period submissions."""
from __future__ import annotations


def _period_signature_from_values(values: list[str]) -> tuple[str, ...]:
    """Canonical business signature, excluding Period ID and updated timestamp."""
    row = [str(item or "").strip() for item in values] + [""] * max(0, 10 - len(values))
    return tuple(row[index] for index in range(1, 9))


def _period_signature_from_record(record: dict[str, object]) -> tuple[str, ...]:
    def date_text(value: object) -> str:
        try:
            return value.strftime("%d/%m/%Y")
        except Exception:
            return str(value or "").strip()

    return (
        str(record.get("worker_id", "") or "").strip(),
        str(record.get("period_type", "") or "").strip(),
        str(record.get("framework", "") or "").strip(),
        str(record.get("subunit", "") or "").strip(),
        str(record.get("location", "") or "").strip(),
        date_text(record.get("start_date")),
        date_text(record.get("end_date")),
        str(record.get("note", "") or "").strip(),
    )


def install(app_module) -> None:
    import tool6_workers as tool6

    if getattr(tool6, "_tool6_period_guard_installed", False):
        return

    original_append_period = tool6._append_period

    def append_period_once(st, values: list[str]) -> None:
        wanted = _period_signature_from_values(values)
        existing = tool6._period_records(tool6._read_period_rows(st))
        if any(_period_signature_from_record(item) == wanted for item in existing):
            raise ValueError("תקופה זהה כבר קיימת לעובד/ת זה/ו. לא נוספה רשומה כפולה.")
        original_append_period(st, values)

    tool6._append_period = append_period_once
    tool6._tool6_period_guard_installed = True
