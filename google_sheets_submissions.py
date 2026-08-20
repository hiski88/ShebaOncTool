"""Central Google Sheets storage for public Tool 1 preference submissions."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

DEFAULT_SPREADSHEET_ID = "1jtnyrbQtB2QXvhS6vU50S24kMDnM1WWcpeFnPmsbYI8"
DEFAULT_SHEET_NAME = "Submissions"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _section(st):
    try:
        return st.secrets.get("google_sheets", {})
    except Exception:
        return {}


def configured(st) -> bool:
    section = _section(st)
    try:
        account = section.get("service_account", {})
        return bool(account.get("client_email") and account.get("private_key"))
    except Exception:
        return False


def _settings(st) -> tuple[str, str, dict]:
    section = _section(st)
    spreadsheet_id = str(section.get("spreadsheet_id", DEFAULT_SPREADSHEET_ID)).strip()
    sheet_name = str(section.get("sheet_name", DEFAULT_SHEET_NAME)).strip() or DEFAULT_SHEET_NAME
    account = dict(section.get("service_account", {}))
    if not account:
        raise RuntimeError("חיבור Google Sheets טרם הוגדר באפליקציה.")
    if "private_key" in account:
        account["private_key"] = str(account["private_key"]).replace("\\n", "\n")
    return spreadsheet_id, sheet_name, account


def _service(st):
    spreadsheet_id, sheet_name, account = _settings(st)
    credentials = service_account.Credentials.from_service_account_info(
        account,
        scopes=SCOPES,
    )
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    return service, spreadsheet_id, sheet_name


def _submission_values(employee: str, year: int, month: int, edited) -> list[str]:
    blocked: list[str] = []
    vacations: list[str] = []
    notes: list[str] = []

    for _, row in edited.iterrows():
        date_value = row.get("תאריך")
        if date_value is None:
            continue
        try:
            day = int(date_value.day)
        except Exception:
            try:
                day = int(date_value.day())
            except Exception:
                continue

        if bool(row.get("חסימה", False)):
            blocked.append(str(day))
        if bool(row.get("חופש", False)):
            vacations.append(str(day))

        note = str(row.get("הערה", "") or "").strip()
        if note:
            notes.append(f"{day:02d}.{month:02d} - {note}")

    submitted_at = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%d.%m.%Y %H:%M:%S")
    month_value = f"{year:04d}-{month:02d}"
    return [
        submitted_at,
        employee.strip(),
        month_value,
        ",".join(blocked),
        ",".join(vacations),
        " | ".join(notes),
    ]


def submit_preferences(st, employee: str, year: int, month: int, edited) -> list[str]:
    """Insert a new submission directly below the header and verify it by reading it back."""
    service, spreadsheet_id, sheet_name = _service(st)
    values = _submission_values(employee, year, month, edited)

    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet = next(
        (item for item in metadata.get("sheets", []) if item.get("properties", {}).get("title") == sheet_name),
        None,
    )
    if sheet is None:
        raise RuntimeError(f"לא נמצאה הכרטיסייה '{sheet_name}' בקובץ Google Sheets.")
    sheet_id = int(sheet["properties"]["sheetId"])

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "insertDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": 1,
                            "endIndex": 2,
                        },
                        "inheritFromBefore": False,
                    }
                }
            ]
        },
    ).execute()

    range_name = f"'{sheet_name}'!A2:F2"
    try:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body={"values": [values]},
        ).execute()
    except Exception:
        try:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "requests": [
                        {
                            "deleteDimension": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "dimension": "ROWS",
                                    "startIndex": 1,
                                    "endIndex": 2,
                                }
                            }
                        }
                    ]
                },
            ).execute()
        except Exception:
            pass
        raise

    check = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    stored = check.get("values", [[]])[0]
    padded = [str(item) for item in stored] + [""] * (6 - len(stored))
    if padded[:6] != values:
        raise RuntimeError("ההגשה נשלחה, אך לא ניתן היה לאמת שהמידע נקלט במלואו.")

    return values


def read_submissions(st, year: int, month: int) -> list[dict[str, str]]:
    """Read Submissions rows for one month, preserving newest-first sheet order."""
    service, spreadsheet_id, sheet_name = _service(st)
    range_name = f"'{sheet_name}'!A2:F"
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueRenderOption="FORMATTED_VALUE",
    ).execute()

    month_value = f"{year:04d}-{month:02d}"
    rows: list[dict[str, str]] = []
    for raw in response.get("values", []):
        values = [str(item) for item in raw] + [""] * (6 - len(raw))
        submitted_at, employee, submitted_month, blocked, vacations, notes = values[:6]
        if submitted_month.strip() != month_value:
            continue
        if not employee.strip():
            continue
        rows.append(
            {
                "זמן הגשה": submitted_at.strip(),
                "שם עובד": employee.strip(),
                "חודש": submitted_month.strip(),
                "חסימות": blocked.strip(),
                "חופשים": vacations.strip(),
                "הערות": notes.strip(),
            }
        )
    return rows
