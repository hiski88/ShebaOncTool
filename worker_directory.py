"""Read-only employee directory used by schedule tools.

Workers is the source of truth for employee identity. Schedule parsers may
match aliases that appear in Excel, but they must not create employee identity.
"""
from __future__ import annotations

from google_sheets_submissions import _service

WORKERS_SHEET = "Workers"


def active_worker_identities(st) -> list[dict[str, object]]:
    """Return active Workers identities and schedule-safe aliases."""
    service, spreadsheet_id, _ = _service(st)
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{WORKERS_SHEET}'!A2:M",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()

    raw_records: list[dict[str, str]] = []
    for raw in response.get("values", []):
        row = [str(item).strip() for item in raw] + [""] * (13 - len(raw))
        worker_id, first_name, last_name = row[0], row[1], row[2]
        status = row[12]
        if not worker_id or not first_name:
            continue
        if status and status != "פעיל":
            continue
        raw_records.append(
            {
                "worker_id": worker_id,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": " ".join(part for part in (first_name, last_name) if part).strip(),
            }
        )

    first_name_counts: dict[str, int] = {}
    for record in raw_records:
        key = record["first_name"].casefold()
        first_name_counts[key] = first_name_counts.get(key, 0) + 1

    result: list[dict[str, object]] = []
    for record in raw_records:
        aliases = [record["full_name"]]
        if first_name_counts.get(record["first_name"].casefold(), 0) == 1:
            aliases.append(record["first_name"])
        result.append(
            {
                **record,
                "aliases": list(dict.fromkeys(alias for alias in aliases if alias)),
            }
        )
    return result


def allowed_schedule_aliases(identities: list[dict[str, object]]) -> list[str]:
    aliases: list[str] = []
    for identity in identities:
        for alias in identity.get("aliases", []):
            value = str(alias or "").strip()
            if value:
                aliases.append(value)
    return list(dict.fromkeys(aliases))
