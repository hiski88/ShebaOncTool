"""Central Google Sheets storage for public Tool 1 preference submissions."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

DEFAULT_SPREADSHEET_ID = "1jtnyrbQtB2QXvhS6vU50S24kMDnM1WWcpeFnPmsbYI8"
DEFAULT_SHEET_NAME = "Submissions"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SUBMISSION_HEADERS = [
    "זמן הגשה",
    "שם עובד",
    "חודש",
    "חסימת תורנות מלאה",
    "חסימת תורנות חצי",
    "חופשים",
    "מעוניין בתורנות",
    "הערה כללית",
]
SUBMISSION_COLUMN_COUNT = len(SUBMISSION_HEADERS)


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


def _submission_values(
    employee: str,
    year: int,
    month: int,
    edited,
    general_note: str = "",
) -> list[str]:
    full_blocks: list[str] = []
    half_blocks: list[str] = []
    vacations: list[str] = []
    wants_duty: list[str] = []

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

        if bool(row.get("חסימת תורנות מלאה", row.get("חסימה", False))):
            full_blocks.append(str(day))
        if bool(row.get("חסימת תורנות חצי", False)):
            half_blocks.append(str(day))
        if bool(row.get("חופש", False)):
            vacations.append(str(day))
        if bool(row.get("מעוניין בתורנות", False)):
            wants_duty.append(str(day))

    submitted_at = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%d.%m.%Y %H:%M:%S")
    month_value = f"{year:04d}-{month:02d}"
    return [
        submitted_at,
        employee.strip(),
        month_value,
        ",".join(full_blocks),
        ",".join(half_blocks),
        ",".join(vacations),
        ",".join(wants_duty),
        str(general_note or "").strip(),
    ]


def submit_preferences(
    st,
    employee: str,
    year: int,
    month: int,
    edited,
    general_note: str = "",
) -> list[str]:
    """Insert a new submission directly below the header and verify it by reading it back."""
    service, spreadsheet_id, sheet_name = _service(st)
    values = _submission_values(employee, year, month, edited, general_note=general_note)

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

    range_name = f"'{sheet_name}'!A2:H2"
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
    padded = [str(item) for item in stored] + [""] * (SUBMISSION_COLUMN_COUNT - len(stored))
    if padded[:SUBMISSION_COLUMN_COUNT] != values:
        raise RuntimeError("ההגשה נשלחה, אך לא ניתן היה לאמת שהמידע נקלט במלואו.")

    return values


def read_submissions(st, year: int, month: int) -> list[dict[str, str]]:
    """Read Submissions rows for one month, preserving newest-first sheet order."""
    service, spreadsheet_id, sheet_name = _service(st)
    range_name = f"'{sheet_name}'!A2:H"
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueRenderOption="FORMATTED_VALUE",
    ).execute()

    month_value = f"{year:04d}-{month:02d}"
    rows: list[dict[str, str]] = []
    for raw in response.get("values", []):
        values = [str(item) for item in raw] + [""] * (SUBMISSION_COLUMN_COUNT - len(raw))
        (
            submitted_at,
            employee,
            submitted_month,
            full_blocks,
            half_blocks,
            vacations,
            wants_duty,
            general_note,
        ) = values[:SUBMISSION_COLUMN_COUNT]
        if submitted_month.strip() != month_value:
            continue
        if not employee.strip():
            continue
        row = {
            "זמן הגשה": submitted_at.strip(),
            "שם עובד": employee.strip(),
            "חודש": submitted_month.strip(),
            "חסימת תורנות מלאה": full_blocks.strip(),
            "חסימת תורנות חצי": half_blocks.strip(),
            "חופשים": vacations.strip(),
            "מעוניין בתורנות": wants_duty.strip(),
            "הערה כללית": general_note.strip(),
        }
        # Temporary compatibility aliases for the existing Tool 2 UI.
        row["חסימות"] = row["חסימת תורנות מלאה"]
        row["הערות"] = row["הערה כללית"]
        rows.append(row)
    return rows


def _day_set(value: str) -> set[int]:
    result: set[int] = set()
    for part in str(value or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.add(int(part))
        except ValueError:
            continue
    return result


def _notes_by_day(value: str) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    for part in str(value or "").split("|"):
        part = part.strip()
        if not part or " - " not in part:
            continue
        date_part, text = part.split(" - ", 1)
        try:
            day = int(date_part.split(".", 1)[0])
        except (TypeError, ValueError):
            continue
        text = text.strip()
        if text:
            result.setdefault(day, []).append(text)
    return result


def _next_planning_title(existing_titles: set[str], year: int, month: int) -> str:
    base = f"{month}-{str(year)[-2:]}"
    if base not in existing_titles:
        return base
    version = 2
    while f"{base} v{version}" in existing_titles:
        version += 1
    return f"{base} v{version}"


def create_planning_sheet(st, year: int, month: int, month_rows, selected_submissions: list[dict[str, str]]) -> str:
    """Create a new versioned RTL monthly planning tab with yellow X cells."""
    if not selected_submissions:
        raise RuntimeError("לא נבחרו הגשות לתכנון.")

    service, spreadsheet_id, _ = _service(st)
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_titles = {
        item.get("properties", {}).get("title", "") for item in metadata.get("sheets", [])
    }
    title = _next_planning_title(existing_titles, year, month)

    employees = [str(item.get("שם עובד", "")).strip() for item in selected_submissions]
    employees = [name for name in employees if name]
    if not employees:
        raise RuntimeError("לא נמצאו שמות עובדים בהגשות שנבחרו.")

    add_result = service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": title,
                            "rightToLeft": True,
                            "gridProperties": {
                                "rowCount": max(40, len(month_rows) + 5),
                                "columnCount": max(12, len(employees) + 5),
                                "frozenRowCount": 1,
                                "frozenColumnCount": 3,
                            },
                        }
                    }
                }
            ]
        },
    ).execute()
    sheet_props = add_result["replies"][0]["addSheet"]["properties"]
    sheet_id = int(sheet_props["sheetId"])

    employee_data = []
    for item in selected_submissions:
        employee_data.append(
            {
                "name": str(item.get("שם עובד", "")).strip(),
                "blocked": _day_set(item.get("חסימות", item.get("חסימת תורנות מלאה", ""))),
                "vacations": _day_set(item.get("חופשים", "")),
                "notes": _notes_by_day(item.get("הערות", "")),
            }
        )

    headers = ["תאריך", "יום", "חג / יום מיוחד", *employees]
    values = [headers]
    cell_notes: list[dict] = []
    x_cells: list[dict] = []

    for row_index, row in enumerate(month_rows, start=1):
        date_value = row.get("תאריך")
        try:
            day = int(date_value.day)
            date_text = date_value.strftime("%d.%m.%Y")
        except Exception:
            day = int(row_index)
            date_text = str(date_value or "")

        output_row = [
            date_text,
            str(row.get("יום", "") or ""),
            str(row.get("חג / יום מיוחד", "") or ""),
        ]
        for employee_col, employee in enumerate(employee_data, start=3):
            blocked = day in employee["blocked"]
            vacation = day in employee["vacations"]
            notes = employee["notes"].get(day, [])
            output_row.append("X" if blocked or vacation else "")

            note_parts: list[str] = []
            if blocked:
                note_parts.append("חסימה")
            if vacation:
                note_parts.append("חופש")
            note_parts.extend(f"הערה: {text}" for text in notes)
            if note_parts:
                cell_notes.append(
                    {
                        "updateCells": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": row_index,
                                "endRowIndex": row_index + 1,
                                "startColumnIndex": employee_col,
                                "endColumnIndex": employee_col + 1,
                            },
                            "rows": [{"values": [{"note": "\n".join(note_parts)}]}],
                            "fields": "note",
                        }
                    }
                )
            if blocked or vacation:
                x_cells.append(
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": row_index,
                                "endRowIndex": row_index + 1,
                                "startColumnIndex": employee_col,
                                "endColumnIndex": employee_col + 1,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.55},
                                    "horizontalAlignment": "CENTER",
                                    "textFormat": {"bold": True},
                                }
                            },
                            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat.bold)",
                        }
                    }
                )
        values.append(output_row)

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{title}'!A1",
        valueInputOption="RAW",
        body={"values": values},
    ).execute()

    format_requests = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(headers),
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.9, "green": 0.93, "blue": 0.97},
                        "horizontalAlignment": "CENTER",
                        "textFormat": {"bold": True},
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat.bold)",
            }
        },
        {
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": len(headers),
                }
            }
        },
        *x_cells,
        *cell_notes,
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": format_requests},
    ).execute()

    return title
