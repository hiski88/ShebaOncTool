"""Monthly planner sheet builder for Tool 2."""
from __future__ import annotations

from google_sheets_submissions import (
    STATUS_FULL_BLOCK,
    STATUS_HALF_BLOCK,
    STATUS_VACATION,
    STATUS_WANTS_DUTY,
    _colored_cell_request,
    _day_set,
    _day_status,
    _next_planning_title,
    _service,
)

PLANNER_HEADERS = ["תורן מחלקה", "תורן א.יום", "תורן מיון"]


def _employee_sort_key(item: dict) -> tuple[int, str]:
    """Sort Hebrew names א-ת first, then Latin names A-Z."""
    name = str(item.get("name", "") or "").strip()
    first_alpha = next((char for char in name if char.isalpha()), "")
    is_hebrew = bool(first_alpha and "א" <= first_alpha <= "ת")
    return (0 if is_hebrew else 1, name.casefold())


def create_planning_sheet(st, year: int, month: int, month_rows, selected_submissions: list[dict[str, str]]) -> str:
    """Create a versioned RTL monthly planning tab with planner fields and visible employee notes."""
    if not selected_submissions:
        raise RuntimeError("לא נבחרו הגשות לתכנון.")

    service, spreadsheet_id, _ = _service(st)
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    existing_titles = {
        item.get("properties", {}).get("title", "") for item in metadata.get("sheets", [])
    }
    title = _next_planning_title(existing_titles, year, month)

    employee_data = []
    for item in selected_submissions:
        name = str(item.get("שם עובד", "") or "").strip()
        if not name:
            continue
        employee_data.append(
            {
                "name": name,
                "full_blocks": _day_set(item.get("חסימת תורנות מלאה", "")),
                "half_blocks": _day_set(item.get("חסימת תורנות חצי", "")),
                "vacations": _day_set(item.get("חופשים", "")),
                "wants_duty": _day_set(item.get("מעוניין בתורנות", "")),
                "general_note": str(item.get("הערה כללית", "") or "").strip(),
            }
        )

    if not employee_data:
        raise RuntimeError("לא נמצאו שמות עובדים בהגשות שנבחרו.")

    employee_data.sort(key=_employee_sort_key)
    employees = [item["name"] for item in employee_data]
    headers = ["תאריך", "יום", "חג / יום מיוחד", *PLANNER_HEADERS, *employees]
    total_columns = len(headers)

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
                                "rowCount": max(44, len(month_rows) + 8),
                                "columnCount": max(12, total_columns + 2),
                                "frozenRowCount": 3,
                                "frozenColumnCount": 6,
                            },
                        }
                    }
                }
            ]
        },
    ).execute()
    sheet_id = int(add_result["replies"][0]["addSheet"]["properties"]["sheetId"])

    legend_row = [
        "מקרא",
        "XX = חופש",
        "½X = חסימת חצי וגם מלאה",
        "X = חסימת מלאה בלבד",
        "V = מעוניין בתורנות",
    ]
    notes_row = ["הערות", "", "", "", "", "", *[item["general_note"] for item in employee_data]]
    values = [legend_row, headers, notes_row]

    format_requests: list[dict] = []
    note_requests: list[dict] = []

    for employee_col, employee in enumerate(employee_data, start=6):
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
        sheet_row_index = data_offset + 3
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
            "",
            "",
            "",
        ]

        for employee_col, employee in enumerate(employee_data, start=6):
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

    for column_index, color in enumerate(
        [STATUS_VACATION[2], STATUS_HALF_BLOCK[2], STATUS_FULL_BLOCK[2], STATUS_WANTS_DUTY[2]],
        start=1,
    ):
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
                        "endColumnIndex": total_columns,
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
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 2,
                        "endRowIndex": 3,
                        "startColumnIndex": 0,
                        "endColumnIndex": total_columns,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.96, "green": 0.96, "blue": 0.96},
                            "verticalAlignment": "TOP",
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,verticalAlignment,wrapStrategy)",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "ROWS",
                        "startIndex": 2,
                        "endIndex": 3,
                    },
                    "properties": {"pixelSize": 64},
                    "fields": "pixelSize",
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
