"""Tool 3 - manager upload of final monthly schedules.

Storage responsibilities are intentionally narrow:
- keep the original spreadsheet bytes unchanged;
- store them in the configured Google Drive archive using a standard name;
- record lightweight catalog metadata in FinalSchedulesIndex.

Schedule parsing/business rules remain outside this module and belong to Tool 4.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd

from google_drive_storage import (
    build_schedule_filename,
    next_schedule_version,
    upload_final_schedule,
    verify_drive_write_cycle,
)
from google_sheets_submissions import _service as sheets_service

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
    preview = preview.iloc[:30, :20].copy()
    return preview.fillna("")


def render(app_module) -> None:
    st = app_module.st
    app_module.render_header(
        "3. העלאת סידור סופי",
        "שמירת הגרסה הסופית של הסידור החודשי בארכיון המרכזי.",
    )

    now = datetime.now(ZoneInfo("Asia/Jerusalem"))
    year_options = list(range(now.year - 1, now.year + 3))
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

    uploaded = st.file_uploader(
        "העלאת קובץ הסידור הסופי",
        type=["xls", "xlsx"],
        key="tool3_final_schedule_file",
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

    st.subheader("תצוגה מקדימה")
    try:
        preview = _preview_excel(content)
        st.dataframe(preview, use_container_width=True, hide_index=True)
        if preview.shape[0] == 30 or preview.shape[1] == 20:
            st.caption("התצוגה המקדימה מוגבלת ל-30 שורות ול-20 עמודות. הקובץ עצמו יישמר במלואו וללא שינוי.")
    except Exception as exc:
        st.warning(f"לא ניתן להציג תצוגה מקדימה של הקובץ: {exc}")
        st.caption("לא בוצע שינוי בקובץ. ניתן לעצור ולבדוק אותו לפני שמירה.")
        return

    try:
        version = next_schedule_version(st, year, month)
        expected_name = build_schedule_filename(year, month, version, extension)
    except Exception as exc:
        st.error(f"לא ניתן לבדוק את גרסת הקובץ הבאה ב-Google Drive: {exc}")
        return

    st.info(f"הקובץ יישמר כ-{expected_name}")

    save_col, _ = st.columns([1, 4])
    with save_col:
        save_clicked = st.button(
            "שמור נתונים",
            type="primary",
            key="tool3_save_final_schedule",
            width="stretch",
        )

    if save_clicked:
        try:
            with st.spinner("שומר את הסידור הסופי ב-Google Drive..."):
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

        index_ok = True
        try:
            append_index_row(st, saved)
        except Exception as exc:
            index_ok = False
            st.warning(
                "הקובץ נשמר בהצלחה ב-Google Drive, אך רישום האינדקס נכשל. "
                f"Tool 4 עדיין יוכל לזהות את הקובץ לפי שמו. פרטי השגיאה: {exc}"
            )

        st.success(f"הסידור נשמר בהצלחה כ-{saved['stored_filename']}")
        if index_ok:
            st.caption("הקובץ נרשם גם ב-FinalSchedulesIndex.")

    with st.expander("בדיקת חיבור ל-Google Drive"):
        st.caption("בדיקה טכנית: יצירת קובץ זמני, קריאתו ומחיקתו.")
        if st.button("הרץ בדיקת כתיבה", key="tool3_drive_write_test"):
            try:
                with st.spinner("בודק כתיבה ל-Google Drive..."):
                    result = verify_drive_write_cycle(st, year)
                st.success(
                    f"הבדיקה הצליחה. התיקייה {result['folder_name']} זמינה לכתיבה, "
                    "קובץ הבדיקה נוצר, נקרא ונמחק בהצלחה."
                )
            except Exception as exc:
                st.error(f"בדיקת הכתיבה ל-Google Drive נכשלה: {exc}")
