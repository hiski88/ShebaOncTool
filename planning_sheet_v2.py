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

PLANNER_HEADERS = ["תורן מחלקה", "תורן א.יום", "תורן מיון", "ביקור שישי", "בחופש"]
SUMMARY_HEADERS = ["שם", "ת.שישי", "ת.שבת", "ביקור שישי", "סה\"כ", "הערות"]

# Only days that function operationally as non-regular workdays should suppress
# day-hospital / ER planner dropdowns. Awareness/family/school markers remain
# visible in the special-day column without disabling regular assignments.
NON_REGULAR_ACTIVITY_TERMS = (
    "ראש השנה",
    "יום כיפור",
    "סוכות",
    "שמיני עצרת",
    "שמחת תורה",
    "פסח",
    "שביעי של פסח",
    "שבועות",
    "יום העצמאות",
    "יום הבחירות לכנסת",
)


def _employee_sort_key(item: dict) -> tuple[int, str]:
    """Sort Hebrew names א-ת first, then Latin names A-Z."""
    name = str(item.get("name", "") or "").strip()
    first_alpha = next((char for char in name if char.isalpha()), "")
    is_hebrew = bool(first_alpha and "א" <= first_alpha <= "ת")
    return (0 if is_hebrew else 1, name.casefold())


def _is_regular_activity_day(row: dict) -> bool:
    day_label = str(row.get("יום", "") or "").strip()
    if day_label in {"ו", "ש"}:
        return False
    special = str(row.get("חג / יום מיוחד", "") or "")
    return not any(term in special for term in NON_REGULAR_ACTIVITY_TERMS)


def create_planning_sheet(st, year: int, month: int, month_rows, selected_submissions: list[dict[str, str]]) -> str:
    """Create a versioned RTL monthly planning tab with live assignment controls and summary."""
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
    fixed_columns = 3 + len(PLANNER_HEADERS)
    total_columns = len(headers)

    month_start_row = 4
    month_end_row = month_start_row + len(month_rows) - 1
    summary_title_row = month_end_row + 2
    summary_header_row = summary_title_row + 1
    summary_first_data_row = summary_header_row + 1
    summary_last_data_row = summary_first_data_row + len(employees) - 1

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
                                "rowCount": max(50, summary_last_data_row + 6),
                                "columnCount": max(12, total_columns + 2),
                                "frozenRowCount": 3,
                                "frozenColumnCount": fixed_columns,
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
    notes_row = ["הערות", *([""] * (fixed_columns - 1)), *[item["general_note"] for item in employee_data]]
    values = [legend_row, headers, notes_row]

    format_requests: list[dict] = []
    note_requests: list[dict] = []

    for employee_col, employee in enumerate(employee_data, start=fixed_columns):
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
            "",
            "",
        ]

        for employee_col, employee in enumerate(employee_data, start=fixed_columns):
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

    summary_values = [["סיכום שיבוצי סוף שבוע"], SUMMARY_HEADERS]
    for offset, employee in enumerate(employees):
        row_number = summary_first_data_row + offset
        summary_values.append(
            [
                employee,
                f'=COUNTIFS($D${month_start_row}:$D${month_end_row},A{row_number},$B${month_start_row}:$B${month_end_row},"ו")',
                f'=COUNTIFS($D${month_start_row}:$D${month_end_row},A{row_number},$B${month_start_row}:$B${month_end_row},"ש")',
                f'=COUNTIFS($G${month_start_row}:$G${month_end_row},A{row_number},$B${month_start_row}:$B${month_end_row},"ו")',
                f'=SUM(B{row_number}:D{row_number})',
                "",
            ]
        )

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{title}'!A{summary_title_row}",
        valueInputOption="USER_ENTERED",
        body={"values": summary_values},
    ).execute()

    for column_index, color in enumerate(
        [STATUS_VACATION[2], STATUS_HALF_BLOCK[2], STATUS_FULL_BLOCK[2], STATUS_WANTS_DUTY[2]],
        start=1,
    ):
        format_requests.append(_colored_cell_request(sheet_id, 0, column_index, color))

    dropdown_values = [{"userEnteredValue": name} for name in employees]
    dropdown_rule = {
        "condition": {"type": "ONE_OF_LIST", "values": dropdown_values},
        "strict": True,
        "showCustomUi": True,
    }

    # Ward duty is relevant every day.
    format_requests.append(
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": month_start_row - 1,
                    "endRowIndex": month_end_row,
                    "startColumnIndex": 3,
                    "endColumnIndex": 4,
                },
                "rule": dropdown_rule,
            }
        }
    )

    # Explicitly clear validation for day-hospital, ER and Friday-visit cells
    # across the whole month before adding it back only where relevant.
    format_requests.append(
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": month_start_row - 1,
                    "endRowIndex": month_end_row,
                    "startColumnIndex": 4,
                    "endColumnIndex": 7,
                }
            }
        }
    )

    # Day-hospital and ER duties are only selectable on regular activity days.
    # Friday visit is selectable only on Fridays. Cells on other days remain blank
    # and have no dropdown, reducing accidental assignments.
    for data_offset, row in enumerate(month_rows):
        row_index = month_start_row - 1 + data_offset
        if _is_regular_activity_day(row):
            format_requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_index,
                            "endRowIndex": row_index + 1,
                            "startColumnIndex": 4,
                            "endColumnIndex": 6,
                        },
                        "rule": dropdown_rule,
                    }
                }
            )
        if str(row.get("יום", "") or "").strip() == "ו":
            format_requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": row_index,
                            "endRowIndex": row_index + 1,
                            "startColumnIndex": 6,
                            "endColumnIndex": 7,
                        },
                        "rule": dropdown_rule,
                    }
                }
            )

    format_requests.extend(
        [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": summary_last_data_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": total_columns,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "textDirection": "RIGHT_TO_LEFT",
                        }
                    },
                    "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,textDirection)",
                }
            },
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
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                            "wrapStrategy": "WRAP",
                            "textDirection": "RIGHT_TO_LEFT",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textDirection)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": summary_title_row - 1,
                        "endRowIndex": summary_title_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(SUMMARY_HEADERS),
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.88, "green": 0.91, "blue": 0.95},
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
                        "startRowIndex": summary_header_row - 1,
                        "endRowIndex": summary_header_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(SUMMARY_HEADERS),
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