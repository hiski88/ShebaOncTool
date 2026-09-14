"""Read the latest centrally stored final schedule for a selected month."""
from __future__ import annotations

from google_drive_storage import drive_service, list_year_files, parse_final_schedule_filename


def select_latest_final_schedule(files: list[dict], year: int, month: int) -> dict | None:
    candidates: list[dict] = []
    for item in files:
        parsed = parse_final_schedule_filename(item.get("name", ""))
        if not parsed:
            continue
        if parsed["year"] != int(year) or parsed["month"] != int(month):
            continue
        candidates.append({**item, **parsed})
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            int(item.get("version", 0)),
            str(item.get("modifiedTime", "") or ""),
            str(item.get("name", "") or ""),
        ),
        reverse=True,
    )
    return candidates[0]


def latest_final_schedule(st, year: int, month: int) -> dict | None:
    return select_latest_final_schedule(list_year_files(st, year), year, month)


def download_final_schedule(st, file_id: str) -> bytes:
    service = drive_service(st)
    content = service.files().get_media(
        fileId=str(file_id),
        supportsAllDrives=True,
    ).execute()
    if not isinstance(content, (bytes, bytearray)):
        raise RuntimeError("Google Drive לא החזיר את תוכן קובץ הסידור בפורמט צפוי.")
    return bytes(content)
