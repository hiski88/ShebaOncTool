"""Pending self-registration records for new managed workers.

WorkerRegistrations is intentionally separate from Workers. A self-registration
contains personal facts supplied by the person and is only promoted to Workers
after manager review. Worker ID is assigned during approval, not while pending,
so IDs cannot be reserved or collide with workers added directly by a manager.
"""
from __future__ import annotations

from datetime import date, datetime
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

from google_sheets_submissions import _service
from system_users import find_worker_by_id_number, normalize_id_number


REGISTRATIONS_SHEET = "WorkerRegistrations"
STATUS_PENDING = "ממתין לאישור"
STATUS_APPROVED = "מאושר"
STATUS_REJECTED = "נדחה"
REGISTRATION_STATUSES = [STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED]

MARITAL_STATUS_OPTIONS = [
    "רווק/ה",
    "בזוגיות / ידוע/ה בציבור",
    "נשוי/אה",
    "פרוד/ה",
    "גרוש/ה",
    "אלמן/ה",
    "אחר",
    "מעדיף/ה לא לציין",
]
CHILDREN_OPTIONS = ["0", "1", "2", "3", "4", "5", "6", "7+"]


def _registrations_service(st):
    service, spreadsheet_id, _ = _service(st)
    return service, spreadsheet_id


def _now_text() -> str:
    return datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%d/%m/%Y %H:%M:%S")


def _new_registration_id() -> str:
    return f"R{uuid4().hex[:10].upper()}"


def _read_registration_rows(st) -> list[list[str]]:
    service, spreadsheet_id = _registrations_service(st)
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{REGISTRATIONS_SHEET}'!A2:Q",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    return response.get("values", [])


def registration_records(st) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for offset, raw in enumerate(_read_registration_rows(st), start=2):
        row = [str(item) for item in raw] + [""] * (17 - len(raw))
        if not row[0].strip():
            continue
        records.append(
            {
                "row_number": str(offset),
                "registration_id": row[0].strip(),
                "status": row[1].strip(),
                "first_name": row[2].strip(),
                "last_name": row[3].strip(),
                "id_number": normalize_id_number(row[4]),
                "birth_date": row[5].strip(),
                "address": row[6].strip(),
                "locality": row[7].strip(),
                "phone": row[8].strip(),
                "email": row[9].strip(),
                "marital_status": row[10].strip(),
                "children": row[11].strip(),
                "submitted_at": row[12].strip(),
                "updated_at": row[13].strip(),
                "reviewed_by": row[14].strip(),
                "manager_note": row[15].strip(),
                "worker_id": row[16].strip(),
            }
        )
    return records


def latest_registration_by_id(st, id_number: str) -> dict[str, str] | None:
    normalized = normalize_id_number(id_number)
    matches = [item for item in registration_records(st) if item.get("id_number") == normalized]
    return matches[-1] if matches else None


def validate_registration_fields(
    *,
    id_number: str,
    first_name: str,
    last_name: str,
    birth_date: date | None,
    address: str,
    locality: str,
    phone: str,
    email: str,
    marital_status: str,
    children: str,
) -> str | None:
    normalized = normalize_id_number(id_number)
    if len(normalized) != 9:
        return "יש להזין תעודת זהות בת 9 ספרות."
    if not first_name.strip():
        return "יש להזין שם פרטי."
    if not last_name.strip():
        return "יש להזין שם משפחה."
    if birth_date is None:
        return "יש להזין תאריך לידה."
    if not address.strip():
        return "יש להזין כתובת."
    if not locality.strip():
        return "יש להזין יישוב מגורים."
    if not phone.strip():
        return "יש להזין מספר טלפון."
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
        return "כתובת האימייל אינה בפורמט תקין."
    if marital_status not in MARITAL_STATUS_OPTIONS:
        return "יש לבחור מצב משפחתי."
    if children not in CHILDREN_OPTIONS:
        return "יש לבחור מספר ילדים."
    return None


def submit_registration(
    st,
    *,
    id_number: str,
    first_name: str,
    last_name: str,
    birth_date: date,
    address: str,
    locality: str,
    phone: str,
    email: str,
    marital_status: str,
    children: str,
) -> dict[str, str]:
    validation_error = validate_registration_fields(
        id_number=id_number,
        first_name=first_name,
        last_name=last_name,
        birth_date=birth_date,
        address=address,
        locality=locality,
        phone=phone,
        email=email,
        marital_status=marital_status,
        children=children,
    )
    if validation_error:
        raise ValueError(validation_error)

    normalized = normalize_id_number(id_number)
    if find_worker_by_id_number(st, normalized) is not None:
        raise ValueError("כבר קיים עובד/ת עם תעודת הזהות הזו. יש לחזור למסך הכניסה.")

    latest = latest_registration_by_id(st, normalized)
    if latest and latest.get("status") in {STATUS_PENDING, STATUS_APPROVED}:
        raise ValueError("כבר קיימת בקשת הצטרפות פעילה עבור תעודת הזהות הזו.")

    registration_id = _new_registration_id()
    now = _now_text()
    values = [
        registration_id,
        STATUS_PENDING,
        first_name.strip(),
        last_name.strip(),
        normalized,
        birth_date.strftime("%d/%m/%Y"),
        address.strip(),
        locality.strip(),
        phone.strip(),
        email.strip(),
        marital_status,
        children,
        now,
        now,
        "",
        "",
        "",
    ]

    service, spreadsheet_id = _registrations_service(st)
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{REGISTRATIONS_SHEET}'!A:Q",
        valueInputOption="RAW",
        insertDataOption="OVERWRITE",
        body={"values": [values]},
    ).execute()

    return {
        "registration_id": registration_id,
        "status": STATUS_PENDING,
        "id_number": normalized,
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "submitted_at": now,
        "worker_id": "",
    }
