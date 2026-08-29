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

# Shared planning visual language.
STATUS_VACATION = ("XX", "חופש - לא זמין לתורנות חצי או מלאה", {"red": 1.0, "green": 0.541, "blue": 0.541})
STATUS_HALF_BLOCK = ("½X", "חסימת תורנות חצי - חוסמת גם תורנות מלאה", {"red": 1.0, "green": 0.749, "blue": 0.412})
STATUS_FULL_BLOCK = ("X", "חסימת תורנות מלאה בלבד", {"red": 1.0, "green": 0.902, "blue": 0.427})
STATUS_WANTS_DUTY = ("V", "מעוניין בתורנות", {"red": 0.545, "green": 0.820, "blue": 0.486})


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
        rows.append(
            {
                "זמן הגשה": submitted_at.strip(),
                "שם עובד": employee.strip(),
                "חודש": submitted_month.strip(),
                "חסימת תורנות מלאה": full_blocks.strip(),
                "חסימת תורנות חצי": half_blocks.strip(),
                "חופשים": vacations.strip(),
                "מעוניין בתורנות": wants_duty.strip(),
                "הערה כללית": general_note.strip(),
            }
        )
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


def _next_planning_title(existing_titles: set[str], year: int, month: int) -> str:
    base = f"{month}-{str(year)[-2:]}"
    if base not in existing_titles:
        return base
    version = 2
    while f"{base} v{version}" in existing_titles:
        version += 1
    return f"{base} v{version}"


def _day_status(day: int, employee: dict) -> tuple[str, str, dict] | None:
    # Priority reflects actual availability and matches Tool 1 preview.
    if day in employee["vacations"]:
        return STATUS_VACATION
    if day in employee["half_blocks"]:
        return STATUS_HALF_BLOCK
    if day in employee["full_blocks"]:
        return STATUS_FULL_BLOCK
    if day in employee["wants_duty"]:
        return STATUS_WANTS_DUTY
    return None


def _colored_cell_request(sheet_id: int, row_index: int, column_index: int, color: dict) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row_index,
                "endRowIndex": row_index + 1,
                "startColumnIndex": column_index,
                "endColumnIndex": column_index + 1,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": color,
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"bold": True},
                }
            },
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat.bold)",
        }
    }


def create_planning_sheet(st, year: int, month: int, month_rows, selected_submissions: list[dict[str, str]]) -> str:
    """Create a new versioned RTL monthly planning tab with a visible legend and colored preference states."""
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

    headers = ["תאריך", "יום", "חג / יום מיוחד", *employees]
    total_columns = max(len(headers), 5)

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
                                "rowCount": max(42, len(month_rows) + 6),
                                "columnCount": max(12, total_columns + 2),
                                "frozenRowCount": 2,
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
                "full_blocks": _day_set(item.get("חסימת תורנות מלאה", "")),
                "half_blocks": _day_set(item.get("חסימת תורנות חצי", "")),
                "vacations": _day_set(item.get("חופשים", "")),
                "wants_duty": _day_set(item.get("מעוניין בתורנות", "")),
                "general_note": str(item.get("הערה כללית", "") or "").strip(),
            }
        )

    legend_row = [
        "מקרא",
        "XX = חופש",
        "½X = חסימת חצי וגם מלאה",
        "X = חסימת מלאה בלבד",
        "V = מעוניין בתורנות",
    ]
    values = [legend_row, headers]
    format_requests: list[dict] = []
    note_requests: list[dict] = []

    # Header notes carry general employee notes without cluttering the grid.
    for employee_col, employee in enumerate(employee_data, start=3):
        if employee["general_note"]:
            note_requests.append(
                {
                    "updateCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 2,
                            "startColumnIndex": employee_col,
                            "endColumnIndex": employee_col + 1,
                        },
                        "rows": [{"values": [{"note": f"הערה כללית: {employee['general_note']}"}]}],
                        "fields": "note",
                    }
                }
            )

    for data_offset, row in enumerate(month_rows):
        sheet_row_index = data_offset + 2
        date_value = row.get("תאריך")
        try:
            day = int(date_value.day)
            date_text = date_value.strftime("%d.%m.%Y")
        except Exception:
            day = data_offset + 1
            date_text = str(date_value or "")

        output_row = [
            date_text,
            str(row.get("יום", "") or ""),
            str(row.get("חג / יום מיוחד", "") or ""),
        ]

        for employee_col, employee in enumerate(employee_data, start=3):
            status = _day_status(day, employee)
            if status is None:
                output_row.append("")
                continue

            symbol, description, color = status
            output_row.append(symbol)
            format_requests.append(_colored_cell_request(sheet_id, sheet_row_index, employee_col, color))
            note_requests.append(
                {
                    "updateCells": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": sheet_row_index,
                            "endRowIndex": sheet_row_index + 1,
                            "startColumnIndex": employee_col,
                            "endColumnIndex": employee_col + 1,
                        },
                        "rows": [{"values": [{"note": description}]}],
                        "fields": "note",
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

    # Legend cells use exactly the same colors as the planning grid.
    legend_colors = [
        STATUS_VACATION[2],
        STATUS_HALF_BLOCK[2],
        STATUS_FULL_BLOCK[2],
        STATUS_WANTS_DUTY[2],
    ]
    for column_index, color in enumerate(legend_colors, start=1):
        format_requests.append(_colored_cell_request(sheet_id, 0, column_index, color))

    format_requests.extend(
        [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.88, "green": 0.91, "blue": 0.95},
                            "horizontalAlignment": "CENTER",
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat.bold)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 2,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(headers),
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.84, "green": 0.88, "blue": 0.94},
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat.bold)",
                }
            },
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": total_columns,
                    }
                }
            },
        ]
    )

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [*format_requests, *note_requests]},
    ).execute()

    return title
