"""System users, permissions and access/audit logging.

This module deliberately separates application identities from managed workers:
- Workers describes people participating in the scheduling model.
- SystemUsers describes people who may access the application.
- Worker ID is an optional link from a system user to a managed worker.
"""
from __future__ import annotations

from datetime import datetime
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

from google_sheets_submissions import _service


SYSTEM_USERS_SHEET = "SystemUsers"
ACCESS_LOG_SHEET = "SystemAccessLog"
AUDIT_LOG_SHEET = "SystemAuditLog"
WORKERS_SHEET = "Workers"

ROLE_EMPLOYEE = "עובד/ת"
ROLE_MANAGER = "מנהל/ת מערכת"
ROLE_ACCESS_ADMIN = "מנהל/ת הרשאות"
SYSTEM_ROLES = [ROLE_EMPLOYEE, ROLE_MANAGER, ROLE_ACCESS_ADMIN]
MANAGER_ROLES = {ROLE_MANAGER, ROLE_ACCESS_ADMIN}

STATUS_ACTIVE = "פעיל"
STATUS_INACTIVE = "לא פעיל"
SYSTEM_STATUSES = [STATUS_ACTIVE, STATUS_INACTIVE]

MANAGER_USER_SESSION_KEY = "medstaff_manager_user_v1"
SESSION_ID_KEY = "medstaff_session_id_v1"


def normalize_id_number(value: object) -> str:
    """Return a normalized 9-digit Israeli-style ID value for matching."""
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    if len(digits) <= 9:
        return digits.zfill(9)
    return digits


def session_id(st) -> str:
    value = str(st.session_state.get(SESSION_ID_KEY, "") or "").strip()
    if not value:
        value = uuid4().hex
        st.session_state[SESSION_ID_KEY] = value
    return value


def _now_text() -> str:
    return datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%d/%m/%Y %H:%M:%S")


def _system_service(st):
    service, spreadsheet_id, _ = _service(st)
    return service, spreadsheet_id


def _read_rows(st, sheet_name: str, column_range: str) -> list[list[str]]:
    service, spreadsheet_id = _system_service(st)
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!{column_range}",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    return response.get("values", [])


def _append_row(st, sheet_name: str, column_range: str, values: list[str]) -> None:
    service, spreadsheet_id = _system_service(st)
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!{column_range}",
        valueInputOption="RAW",
        insertDataOption="OVERWRITE",
        body={"values": [values]},
    ).execute()


def _new_id(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:10].upper()}"


def list_users(st) -> list[dict[str, str]]:
    rows = _read_rows(st, SYSTEM_USERS_SHEET, "A2:J")
    users: list[dict[str, str]] = []
    for offset, raw in enumerate(rows, start=2):
        row = [str(item) for item in raw] + [""] * (10 - len(raw))
        if not row[0].strip():
            continue
        users.append(
            {
                "user_id": row[0].strip(),
                "id_number": normalize_id_number(row[1]),
                "display_name": row[2].strip(),
                "role": row[3].strip(),
                "worker_id": row[4].strip(),
                "status": row[5].strip(),
                "created_at": row[6].strip(),
                "created_by": row[7].strip(),
                "updated_at": row[8].strip(),
                "note": row[9].strip(),
                "row_number": str(offset),
            }
        )
    return users


def lookup_user_by_id(st, id_number: str) -> dict[str, str] | None:
    normalized = normalize_id_number(id_number)
    if len(normalized) != 9:
        return None
    matches = [user for user in list_users(st) if user.get("id_number") == normalized]
    if len(matches) > 1:
        raise RuntimeError("נמצאו מספר משתמשי מערכת עם אותה ת.ז. יש לתקן את טבלת SystemUsers.")
    return matches[0] if matches else None


def get_user_by_user_id(st, user_id: str) -> dict[str, str] | None:
    wanted = str(user_id or "").strip()
    for user in list_users(st):
        if user.get("user_id") == wanted:
            return user
    return None


def manager_users_exist(st) -> bool:
    return any(user.get("role") in MANAGER_ROLES for user in list_users(st))


def active_access_admin_count(st) -> int:
    return sum(
        1
        for user in list_users(st)
        if user.get("role") == ROLE_ACCESS_ADMIN and user.get("status") == STATUS_ACTIVE
    )


def find_worker_by_id_number(st, id_number: str) -> dict[str, str] | None:
    normalized = normalize_id_number(id_number)
    if len(normalized) != 9:
        return None
    rows = _read_rows(st, WORKERS_SHEET, "A2:S")
    matches: list[dict[str, str]] = []
    for raw in rows:
        row = [str(item) for item in raw] + [""] * (19 - len(raw))
        if normalize_id_number(row[3]) != normalized:
            continue
        first_name = row[1].strip()
        last_name = row[2].strip()
        matches.append(
            {
                "worker_id": row[0].strip(),
                "id_number": normalized,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": " ".join(part for part in (first_name, last_name) if part).strip(),
                "status": row[12].strip(),
            }
        )
    if len(matches) > 1:
        raise RuntimeError("נמצאו מספר עובדים עם אותה ת.ז. יש לתקן את טבלת Workers.")
    return matches[0] if matches else None


def log_access(
    st,
    *,
    user: dict[str, str] | None,
    entry_type: str,
    result: str,
) -> None:
    user = user or {}
    _append_row(
        st,
        ACCESS_LOG_SHEET,
        "A:H",
        [
            _new_id("L"),
            str(user.get("user_id", "UNKNOWN") or "UNKNOWN"),
            str(user.get("worker_id", "") or ""),
            str(user.get("display_name", "") or ""),
            _now_text(),
            str(entry_type or ""),
            str(result or ""),
            session_id(st),
        ],
    )


def log_audit(
    st,
    *,
    actor_user_id: str,
    action: str,
    target_type: str,
    target_id: str,
    details: str = "",
) -> None:
    _append_row(
        st,
        AUDIT_LOG_SHEET,
        "A:H",
        [
            _new_id("A"),
            str(actor_user_id or "SYSTEM"),
            _now_text(),
            str(action or ""),
            str(target_type or ""),
            str(target_id or ""),
            str(details or ""),
            session_id(st),
        ],
    )


def create_system_user(
    st,
    *,
    id_number: str,
    display_name: str,
    role: str,
    worker_id: str = "",
    created_by: str = "SYSTEM",
    note: str = "",
) -> dict[str, str]:
    normalized = normalize_id_number(id_number)
    if len(normalized) != 9:
        raise ValueError("יש להזין תעודת זהות בת 9 ספרות.")
    if not str(display_name or "").strip():
        raise ValueError("יש להזין שם לתצוגה.")
    if role not in SYSTEM_ROLES:
        raise ValueError("תפקיד המערכת אינו תקין.")
    if lookup_user_by_id(st, normalized) is not None:
        raise ValueError("כבר קיים משתמש מערכת עם תעודת הזהות הזו.")

    user_id = _new_id("U")
    now = _now_text()
    values = [
        user_id,
        normalized,
        str(display_name).strip(),
        role,
        str(worker_id or "").strip(),
        STATUS_ACTIVE,
        now,
        str(created_by or "SYSTEM").strip() or "SYSTEM",
        now,
        str(note or "").strip(),
    ]
    _append_row(st, SYSTEM_USERS_SHEET, "A:J", values)
    log_audit(
        st,
        actor_user_id=str(created_by or "SYSTEM"),
        action="יצירת משתמש מערכת",
        target_type="SystemUser",
        target_id=user_id,
        details=f"תפקיד: {role}; Worker ID: {str(worker_id or '').strip() or '-'}",
    )
    return {
        "user_id": user_id,
        "id_number": normalized,
        "display_name": str(display_name).strip(),
        "role": role,
        "worker_id": str(worker_id or "").strip(),
        "status": STATUS_ACTIVE,
        "created_at": now,
        "created_by": str(created_by or "SYSTEM"),
        "updated_at": now,
        "note": str(note or "").strip(),
    }


def update_system_user(
    st,
    *,
    user_id: str,
    display_name: str,
    role: str,
    worker_id: str,
    status: str,
    note: str,
    actor_user_id: str,
) -> dict[str, str]:
    if role not in SYSTEM_ROLES:
        raise ValueError("תפקיד המערכת אינו תקין.")
    if status not in SYSTEM_STATUSES:
        raise ValueError("סטטוס המשתמש אינו תקין.")
    if not str(display_name or "").strip():
        raise ValueError("יש להזין שם לתצוגה.")

    current = get_user_by_user_id(st, user_id)
    if current is None:
        raise ValueError("משתמש המערכת לא נמצא.")

    row_number = int(current["row_number"])
    now = _now_text()
    values = [
        current["user_id"],
        current["id_number"],
        str(display_name).strip(),
        role,
        str(worker_id or "").strip(),
        status,
        current["created_at"],
        current["created_by"],
        now,
        str(note or "").strip(),
    ]
    service, spreadsheet_id = _system_service(st)
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{SYSTEM_USERS_SHEET}'!A{row_number}:J{row_number}",
        valueInputOption="RAW",
        body={"values": [values]},
    ).execute()

    details = (
        f"תפקיד: {current.get('role', '')} -> {role}; "
        f"סטטוס: {current.get('status', '')} -> {status}; "
        f"Worker ID: {current.get('worker_id', '') or '-'} -> {str(worker_id or '').strip() or '-'}"
    )
    log_audit(
        st,
        actor_user_id=actor_user_id,
        action="עדכון משתמש מערכת",
        target_type="SystemUser",
        target_id=current["user_id"],
        details=details,
    )
    return {
        **current,
        "display_name": str(display_name).strip(),
        "role": role,
        "worker_id": str(worker_id or "").strip(),
        "status": status,
        "updated_at": now,
        "note": str(note or "").strip(),
    }


def ensure_employee_user(st, worker: dict[str, str]) -> dict[str, str]:
    """Return the SystemUser for an active worker, provisioning it on first login."""
    id_number = normalize_id_number(worker.get("id_number", ""))
    existing = lookup_user_by_id(st, id_number)
    if existing is None:
        return create_system_user(
            st,
            id_number=id_number,
            display_name=str(worker.get("full_name", "") or "").strip(),
            role=ROLE_EMPLOYEE,
            worker_id=str(worker.get("worker_id", "") or "").strip(),
            created_by="SYSTEM",
            note="נוצר אוטומטית בכניסת העובד/ת הראשונה",
        )

    desired_worker_id = str(worker.get("worker_id", "") or "").strip()
    if desired_worker_id and existing.get("worker_id") != desired_worker_id:
        existing = update_system_user(
            st,
            user_id=existing["user_id"],
            display_name=existing.get("display_name") or str(worker.get("full_name", "") or "").strip(),
            role=existing.get("role") or ROLE_EMPLOYEE,
            worker_id=desired_worker_id,
            status=existing.get("status") or STATUS_ACTIVE,
            note=existing.get("note", ""),
            actor_user_id="SYSTEM",
        )
    return existing


def read_access_log(st, limit: int = 200) -> list[dict[str, str]]:
    rows = _read_rows(st, ACCESS_LOG_SHEET, "A2:H")
    output: list[dict[str, str]] = []
    for raw in reversed(rows[-max(1, int(limit)):]):
        row = [str(item) for item in raw] + [""] * (8 - len(raw))
        if not row[0].strip():
            continue
        output.append(
            {
                "Log ID": row[0].strip(),
                "User ID": row[1].strip(),
                "Worker ID": row[2].strip(),
                "שם": row[3].strip(),
                "תאריך ושעת כניסה": row[4].strip(),
                "סוג כניסה": row[5].strip(),
                "תוצאה": row[6].strip(),
                "Session ID": row[7].strip(),
            }
        )
    return output


def read_audit_log(st, limit: int = 200) -> list[dict[str, str]]:
    rows = _read_rows(st, AUDIT_LOG_SHEET, "A2:H")
    output: list[dict[str, str]] = []
    for raw in reversed(rows[-max(1, int(limit)):]):
        row = [str(item) for item in raw] + [""] * (8 - len(raw))
        if not row[0].strip():
            continue
        output.append(
            {
                "Audit ID": row[0].strip(),
                "User ID": row[1].strip(),
                "תאריך ושעה": row[2].strip(),
                "פעולה": row[3].strip(),
                "סוג יעד": row[4].strip(),
                "מזהה יעד": row[5].strip(),
                "פרטים": row[6].strip(),
                "Session ID": row[7].strip(),
            }
        )
    return output
