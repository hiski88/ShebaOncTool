"""Tool 3 - monthly schedule browsing and manager-only publishing.

Read path:
- any authenticated user may browse stored monthly schedules;
- selecting a stored version downloads it read-only from the central Drive archive.

Write path:
- only an authenticated manager may upload and publish a new official version;
- original spreadsheet bytes are preserved unchanged;
- the uploaded month/year is verified before archiving;
- published versions are catalogued in FinalSchedulesIndex.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd

from final_schedule_reader import download_final_schedule, list_final_schedules
from google_drive_storage import (
    build_schedule_filename,
    next_schedule_version,
    upload_final_schedule,
    verify_drive_write_cycle,
)
from google_sheets_submissions import _service as sheets_service
from schedule_parser import detect_month_year, read_schedule_workbook
from system_users import MANAGER_ROLES, MANAGER_USER_SESSION_KEY, STATUS_ACTIVE

INDEX_SHEET_NAME = "FinalSchedulesIndex"
INDEX_HEADERS = [
    "uploaded_at",
    "year",
    "month",
    "version",
    "stored_filename",
    "original_filename",
    "drive_file_id",
    "source",
]
MONTH_NAMES = [
    "ינואר",
    "פברואר",
    "מרץ",
    "אפריל",
    "מאי",
    "יוני",
    "יולי",
    "אוגוסט",
    "ספטמבר",
    "אוקטובר",
    "נובמבר",
    "דצמבר",
]


def _current_user_is_manager(st) -> bool:
    user = st.session_state.get(MANAGER_USER_SESSION_KEY)
    if not isinstance(user, dict):
        return False
    if bool(user.get("bootstrap")):
        return True
    return user.get("status") == STATUS_ACTIVE and user.get("role") in MANAGER_ROLES


def _ensure_index_sheet(st) -> tuple[object, str]:
    service, spreadsheet_id, _ = sheets_service(st)
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheet = next(
        (
            item
            for item in metadata.get("sheets", [])
            if item.get("properties", {}).get("title") == INDEX_SHEET_NAME
        ),
        None,
    )

    if sheet is None:
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": INDEX_SHEET_NAME,
                                "rightToLeft": False,
                                "gridProperties": {
                                    "rowCount": 1000,
                                    "columnCount": len(INDEX_HEADERS),
                                    "frozenRowCount": 1,
                                },
                            }
                        }
                    }
                ]
            },
        ).execute()
        sheet_id = int(result["replies"][0]["addSheet"]["properties"]["sheetId"])
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{INDEX_SHEET_NAME}'!A1:H1",
            valueInputOption="RAW",
            body={"values": [INDEX_HEADERS]},
        ).execute()
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": 1,
                                "startColumnIndex": 0,
                                "endColumnIndex": len(INDEX_HEADERS),
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "textFormat": {"bold": True},
                                    "horizontalAlignment": "CENTER",
                                }
                            },
                            "fields": "userEnteredFormat(textFormat.bold,horizontalAlignment)",
                        }
                    }
                ]
            },
        ).execute()
    return service, spreadsheet_id


def append_index_row(st, saved: dict) -> None:
    service, spreadsheet_id = _ensure_index_sheet(st)
    uploaded_at = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%d.%m.%Y %H:%M:%S")
    row = [
        uploaded_at,
        int(saved["year"]),
        int(saved["month"]),
        f"V{int(saved['version'])}",
        saved["stored_filename"],
        saved["original_filename"],
        saved["id"],
        "tool3",
    ]
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{INDEX_SHEET_NAME}'!A:H",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


def _preview_excel(content: bytes) -> pd.DataFrame:
    preview = pd.read_excel(BytesIO(content), sheet_name=0, header=None)
    preview = preview.iloc[:60, :30].copy()
    return preview.fillna("")


def _detect_uploaded_period(content: bytes, filename: str, config: dict) -> tuple[int, int] | None:
    workbook = read_schedule_workbook(content, filename)
    sheet = workbook.sheet_by_preference(config.get("schedule", {}).get("sheet_names", []))
    return detect_month_year(sheet, config)


def _render_saved_schedule_browser(st, app_module, year: int, month: int) -> None:
    st.subheader("לו״זים שמורים")
    try:
        schedules = list_final_schedules(st, year, month)
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את ארכיון הלו״זים: {exc}")
        return

    if not schedules:
        st.info(f"לא נמצא לו״ז שמור עבור {MONTH_NAMES[month - 1]} {year}.")
        return

    labels = []
    by_label = {}
    for item in schedules:
        version = int(item.get("version", 0) or 0)
        name = str(item.get("name", "") or "")
        modified = str(item.get("modifiedTime", "") or "")
        label = f"V{version} - {name}"
        if modified:
            label += f" - {modified[:10]}"
        labels.append(label)
        by_label[label] = item

    selected_label = st.selectbox(
        "בחירת גרסה שמורה",
        labels,
        index=0,
        key=f"tool3_saved_version_{year}_{month}",
    )
    selected = by_label[selected_label]

    try:
        content = download_final_schedule(st, str(selected.get("id", "") or ""))
    except Exception as exc:
        st.error(f"לא ניתן לטעון את הלו״ז שנבחר: {exc}")
        return

    st.caption(
        f"גרסה V{int(selected.get('version', 0) or 0)} | "
        f"{str(selected.get('name', '') or '')}"
    )

    try:
        preview = _preview_excel(content)
        st.dataframe(preview, width="stretch", hide_index=True)
        if preview.shape[0] == 60 or preview.shape[1] == 30:
            st.caption("התצוגה מוגבלת ל-60 שורות ול-30 עמודות.")
    except Exception as exc:
        st.warning(f"לא ניתן להציג תצוגה מקדימה של הלו״ז: {exc}")


def _render_manager_publish(st, app_module, year: int, month: int) -> None:
    st.subheader("העלאה ופרסום")
    st.caption(
        "פעולה מנהלית בלבד. פרסום יוצר גרסה רשמית חדשה בארכיון Google Drive."
    )

    month_name = MONTH_NAMES[month - 1]
    uploaded = st.file_uploader(
        "העלאת קובץ לו״ז",
        type=["xls", "xlsx"],
        key=f"tool3_final_schedule_file_{year}_{month}",
        help="הקובץ המקורי נשמר ללא המרה או שינוי.",
    )
    if uploaded is None:
        return

    content = uploaded.getvalue()
    original_name = str(uploaded.name or "")
    extension = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""

    if extension not in {"xls", "xlsx"}:
        st.error("ניתן להעלות רק קבצי XLS או XLSX.")
        return

    try:
        detected_period = _detect_uploaded_period(content, original_name, app_module.CONFIG)
    except Exception as exc:
        st.error(f"לא ניתן לאמת לאיזה חודש שייך הקובץ: {exc}")
        return

    if detected_period is None:
        st.error(
            "לא ניתן לזהות באופן אמין את החודש והשנה מתוך הלו״ז. "
            "הקובץ לא יישמר עד שניתן יהיה לאמת את החודש שלו."
        )
        return

    detected_year, detected_month = detected_period
    detected_name = MONTH_NAMES[detected_month - 1]
    if (detected_year, detected_month) != (year, month):
        st.error(
            f"הקובץ מזוהה כלו״ז של {detected_name} {detected_year}, "
            f"אך במסך נבחר {month_name} {year}."
        )
        return

    st.success(f"אומת שהקובץ שייך ל-{detected_name} {detected_year}.")

    try:
        preview = _preview_excel(content)
        st.dataframe(preview, width="stretch", hide_index=True)
    except Exception as exc:
        st.warning(f"לא ניתן להציג תצוגה מקדימה של הקובץ: {exc}")
        return

    try:
        version = next_schedule_version(st, year, month)
        expected_name = build_schedule_filename(year, month, version, extension)
    except Exception as exc:
        st.error(f"לא ניתן לבדוק את גרסת הקובץ הבאה ב-Google Drive: {exc}")
        return

    st.info(f"הגרסה החדשה תישמר כ-{expected_name}")

    save_clicked = st.button(
        "פרסם ושמור ב-Google Drive",
        type="primary",
        key=f"tool3_save_final_schedule_{year}_{month}",
    )
    if save_clicked:
        if not _current_user_is_manager(st):
            st.error("רק מנהל/ת מערכת רשאי/ת לפרסם ולשמור לו״ז רשמי.")
            return
        try:
            saved = upload_final_schedule(
                st,
                year=year,
                month=month,
                original_filename=original_name,
                content=content,
            )
        except Exception as exc:
            st.error(f"שמירת הקובץ ב-Google Drive נכשלה: {exc}")
            return

        try:
            append_index_row(st, saved)
        except Exception as exc:
            st.warning(
                "הקובץ נשמר ב-Google Drive, אך רישום האינדקס נכשל. "
                f"פרטי השגיאה: {exc}"
            )
        st.success(f"הלו״ז נשמר בהצלחה כ-{saved['stored_filename']}")
        st.rerun()

    with st.expander("בדיקת חיבור ל-Google Drive"):
        if st.button("הרץ בדיקת כתיבה", key=f"tool3_drive_write_test_{year}_{month}"):
            try:
                result = verify_drive_write_cycle(st, year)
                st.success(
                    f"הבדיקה הצליחה. התיקייה {result['folder_name']} זמינה לכתיבה."
                )
            except Exception as exc:
                st.error(f"בדיקת הכתיבה ל-Google Drive נכשלה: {exc}")


def render(app_module) -> None:
    st = app_module.st
    app_module.render_header(
        "3. לו״ז חודשי",
        "בחירה וצפייה בגרסאות לו״ז שנשמרו במערכת. מנהלים יכולים גם לפרסם גרסה רשמית חדשה.",
    )

    now = datetime.now(ZoneInfo("Asia/Jerusalem"))
    year_options = list(range(now.year - 2, now.year + 3))
    year_default = year_options.index(now.year)

    selector_col1, selector_col2, _ = st.columns([1, 1, 4])
    with selector_col1:
        year = int(
            st.selectbox(
                "שנה",
                options=year_options,
                index=year_default,
                key="tool3_final_year",
            )
        )
    with selector_col2:
        month_name = st.selectbox(
            "חודש",
            options=MONTH_NAMES,
            index=now.month - 1,
            key="tool3_final_month",
        )
        month = MONTH_NAMES.index(month_name) + 1

    _render_saved_schedule_browser(st, app_module, year, month)

    if _current_user_is_manager(st):
        st.divider()
        _render_manager_publish(st, app_module, year, month)
