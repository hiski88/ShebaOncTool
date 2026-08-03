from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from core import (
    HEBREW_MONTHS,
    add_months,
    availability_matrix,
    availability_summary,
    build_month_table,
    build_submission,
    encode_submission,
    events_to_ics,
    load_config,
    records_to_events,
)
from excel_tools import (
    build_manager_workbook,
    build_personal_submission_workbook,
    build_response_collection_template,
    build_schedule_analysis_workbook,
    build_schedule_template,
    parse_response_collection,
)
from google_calendar import (
    authorization_url,
    build_service,
    create_events,
    disconnect,
    get_credentials,
    handle_oauth_callback,
    list_writable_calendars,
    oauth_configured,
    oauth_dependencies_available,
)
from schedule_parser import (
    infer_employee_names,
    parse_schedule,
    read_schedule_workbook,
    summarize_schedule,
    validate_schedule,
)

ROOT = Path(__file__).resolve().parent
CONFIG = load_config(ROOT / "config" / "oncology.json")

st.set_page_config(
    page_title=CONFIG["app_title"],
    page_icon="🗓️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    html, body, .stApp, [data-testid="stAppViewContainer"] { direction: rtl; text-align: right; }
    .main .block-container { max-width: 1500px; padding-top: 1.25rem; }
    h1, h2, h3, p, label { text-align: right; }
    div[data-testid="stHorizontalBlock"] { direction: rtl; }
    div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] { direction: rtl; }
    section[data-testid="stSidebar"] { direction: rtl; text-align: right; }
    .hero { padding: 1.1rem 1.25rem; border: 1px solid #e6ebf2; border-radius: 18px; background: #fbfcff; margin-bottom: 1rem; }
    .hero h1 { margin: 0 0 .35rem 0; font-size: 1.9rem; }
    .hero p { margin: 0; color: #596579; }
    .privacy { padding: .8rem 1rem; border-radius: 12px; background: #fff8e6; border: 1px solid #f2d891; }
    @media (max-width: 768px) {
      .main .block-container { padding: .8rem .6rem 4rem .6rem; }
      button { min-height: 44px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

connected, callback_error = handle_oauth_callback(st)
if callback_error:
    st.error(callback_error)
elif connected:
    st.success("החיבור ליומן Google הושלם.")


def month_selector(key: str, offset: int = 1) -> tuple[int, int]:
    default = add_months(date.today().replace(day=1), offset)
    col_year, col_month = st.columns([1, 1])
    with col_year:
        year = st.selectbox(
            "שנה",
            list(range(date.today().year - 1, date.today().year + 5)),
            index=list(range(date.today().year - 1, date.today().year + 5)).index(default.year),
            key=f"{key}_year",
        )
    with col_month:
        month = st.selectbox(
            "חודש",
            list(range(1, 13)),
            index=default.month - 1,
            format_func=lambda number: HEBREW_MONTHS[number],
            key=f"{key}_month",
        )
    return int(year), int(month)


def render_header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def event_dataframe(events) -> pd.DataFrame:
    rows = []
    for event in events:
        rows.append(
            {
                "תאריך": event.event_date,
                "אירוע": event.title,
                "כל היום": event.all_day,
                "התחלה": "" if event.all_day or event.start is None else event.start.strftime("%d.%m.%Y %H:%M"),
                "סיום": "" if event.all_day or event.end is None else event.end.strftime("%d.%m.%Y %H:%M"),
                "קוד מטלה": event.task_code,
            }
        )
    return pd.DataFrame(rows)


def tool_preferences() -> None:
    render_header(
        "1. תכנון העדפות אישיות",
        "העובד/ת מסמן/ת אי זמינות וחופש ומקבל/ת פלט אחד להדבקה בקובץ הריכוז.",
    )
    year, month = month_selector("preferences", offset=1)
    employee = st.text_input("שם עובד/ת", placeholder="שם מלא", key="preferences_employee")

    table = build_month_table(year, month)
    table["לא זמין"] = False
    table["חופש"] = False
    table["הערה"] = ""
    edited = st.data_editor(
        table,
        width="stretch",
        hide_index=True,
        disabled=["תאריך", "יום", "חג / יום מיוחד"],
        column_config={
            "תאריך": st.column_config.DateColumn("תאריך", format="DD.MM.YYYY"),
            "לא זמין": st.column_config.CheckboxColumn("לא זמין"),
            "חופש": st.column_config.CheckboxColumn("חופש"),
            "הערה": st.column_config.TextColumn("הערה"),
        },
        key=f"preferences_table_{year}_{month}",
    )

    overlap = edited[edited["לא זמין"] & edited["חופש"]]
    if not overlap.empty:
        st.warning("יש תאריכים שסומנו גם כחופש וגם כלא זמינים. המערכת תשמור את שני הסימונים.")

    if employee.strip():
        try:
            payload = build_submission(employee, year, month, edited)
            output = encode_submission(payload)
            st.subheader("פלט להעברה למתכנן")
            st.text_area(
                "יש להעתיק את כל התוכן",
                value=output,
                height=180,
                key=f"preferences_output_{year}_{month}_{employee}",
            )
            workbook = build_personal_submission_workbook(employee, edited, output)
            st.download_button(
                "הורדת ההעדפות כקובץ Excel",
                data=workbook,
                file_name=f"העדפות_{employee}_{year}_{month:02d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        except Exception as exc:
            st.error(str(exc))
    else:
        st.info("לאחר הזנת שם, הפלט וקובץ ההורדה יופקו אוטומטית.")


def tool_manager() -> None:
    render_header(
        "2. ריכוז העדפות ובניית לוז",
        "המתכנן מעלה קובץ אחד עם כל תשובות הצוות ומקבל טבלת זמינות וקובץ עבודה חודשי.",
    )
    year, month = month_selector("manager", offset=1)

    col_a, col_b = st.columns(2)
    with col_a:
        response_template = build_response_collection_template(year, month)
        st.download_button(
            "הורדת תבנית לריכוז תשובות הצוות",
            data=response_template,
            file_name=f"ריכוז_תשובות_{year}_{month:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    with col_b:
        blank_schedule = build_schedule_template(year, month, CONFIG)
        st.download_button(
            "הורדת תבנית לוז אונקולוגיה",
            data=blank_schedule,
            file_name=f"לוז_אונקולוגיה_{year}_{month:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )

    st.divider()
    responses_file = st.file_uploader(
        "העלאת קובץ ריכוז התשובות",
        type=["xlsx", "csv"],
        key="manager_responses",
    )
    schedule_template_file = st.file_uploader(
        "אפשרות נוספת: העלאת תבנית לוז קיימת מסוג XLSX",
        type=["xlsx"],
        key="manager_schedule_template",
        help="טבלאות הזמינות והסיכום יתווספו לקובץ בלי למחוק את גיליון הלוז.",
    )

    if responses_file is None:
        st.info("העלה את קובץ הריכוז לאחר שהודבקו בו תשובות הצוות.")
        return

    try:
        payloads, warnings = parse_response_collection(responses_file.getvalue(), responses_file.name)
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את קובץ התשובות: {exc}")
        return

    for warning in warnings:
        st.warning(warning)
    matching = [payload for payload in payloads if payload.get("month") == f"{year:04d}-{month:02d}"]
    mismatched = [payload for payload in payloads if payload.get("month") != f"{year:04d}-{month:02d}"]
    if mismatched:
        names = ", ".join(str(item.get("employee")) for item in mismatched)
        st.warning(f"התשובות הבאות שייכות לחודש אחר ולא נכללו: {names}")
    if not matching:
        st.error("לא נמצאו תשובות תקינות לחודש שנבחר.")
        return

    matrix = availability_matrix(matching, year, month)
    summary = availability_summary(matching)
    st.success(f"נקלטו {len(matching)} תשובות תקינות.")
    st.subheader("טבלת זמינות צוות")
    st.dataframe(matrix, width="stretch", hide_index=True)
    st.subheader("סיכום")
    st.dataframe(summary, width="stretch", hide_index=True)

    try:
        output = build_manager_workbook(
            matching,
            year,
            month,
            CONFIG,
            uploaded_template=schedule_template_file.getvalue() if schedule_template_file else None,
        )
        st.download_button(
            "הורדת קובץ העבודה המלא",
            data=output,
            file_name=f"קובץ_עבודה_אונקולוגיה_{year}_{month:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    except Exception as exc:
        st.error(f"לא ניתן היה לבנות את קובץ העבודה: {exc}")


def tool_calendar() -> None:
    render_header(
        "3. לוז סופי ושמירה ביומן",
        "מעלים לוז סופי, בוחרים עובד/ת, בודקים את המטלות ומורידים ICS או יוצרים אירועים ישירות ביומן Google.",
    )
    uploaded = st.file_uploader(
        "העלאת לוז סופי",
        type=["xls", "xlsx", "xlsm"],
        key="final_schedule",
    )
    if uploaded is None:
        st.info("המערכת תומכת ב-XLS וב-XLSX. ב-XLSX זיהוי עיצובי מחיקה אמין יותר, וב-XLS נעשה שימוש גם במידע העיצובי הישן של Excel.")
        return

    try:
        workbook = read_schedule_workbook(uploaded.getvalue(), uploaded.name)
        inferred = infer_employee_names(workbook, CONFIG)
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את הלוז: {exc}")
        return

    st.caption(f"זוהו אוטומטית {len(inferred)} שמות אפשריים.")
    additional = st.text_area(
        "תיקון רשימת שמות, במידת הצורך",
        placeholder="שם נוסף בכל שורה",
        help="אין צורך להעתיק את השמות שכבר זוהו. הזן כאן רק שמות חסרים.",
        key="additional_names",
    )
    additional_names = [line.strip() for line in additional.splitlines() if line.strip()]
    names = sorted(set(inferred + additional_names))
    if not names:
        st.warning("לא זוהו שמות. יש להזין לפחות שם אחד בשדה התיקון.")
        return

    employee = st.selectbox("בחירת עובד/ת", names, key="calendar_employee")
    try:
        records = parse_schedule(workbook, CONFIG, names)
    except Exception as exc:
        st.error(f"פענוח הלוז נכשל: {exc}")
        return

    selected = records[records["employee"] == employee].copy()
    summary = summarize_schedule(records)
    validation = validate_schedule(records, CONFIG)
    events = records_to_events(records, employee, CONFIG)
    event_table = event_dataframe(events)

    st.subheader(f"מטלות וסטטוסים שזוהו עבור {employee}")
    display_columns = {
        "date": "תאריך",
        "day": "יום",
        "holiday": "חג / יום מיוחד",
        "record_type": "סוג רשומה",
        "task_label": "מטלה / סטטוס",
        "subtype": "פירוט",
        "source_cell": "תא מקור",
        "raw_text": "תוכן מקורי",
    }
    display = selected[list(display_columns)].rename(columns=display_columns)
    st.dataframe(display, width="stretch", hide_index=True)

    st.subheader("סיכום מטלות אוטומטי")
    st.dataframe(summary, width="stretch", hide_index=True)

    st.subheader("בדיקות איוש אוטומטיות")
    if validation.empty:
        st.success("לא נמצאו חריגות לפי כללי האיוש שהוגדרו.")
    else:
        st.warning(f"נמצאו {len(validation)} חריגות לבדיקה לפני פרסום הלוז.")
        st.dataframe(validation, width="stretch", hide_index=True)

    st.subheader("אירועים מוצעים ליומן")
    st.info("פעילויות יום מוגדרות בפרוטוטייפ כאירועי יום שלם. שעות התורנויות הן ברירות מחדל קונפיגורביליות ויש לאמת אותן לפני שימוש שוטף.")
    st.dataframe(event_table, width="stretch", hide_index=True)

    ics = events_to_ics(events, CONFIG.get("timezone", "Asia/Jerusalem"))
    st.download_button(
        "הורדת קובץ ICS",
        data=ics,
        file_name=f"לוז_{employee}.ics",
        mime="text/calendar",
        width="stretch",
        disabled=not events,
    )

    analysis_file = build_schedule_analysis_workbook(selected, summary, event_table, validation)
    st.download_button(
        "הורדת דוח פענוח Excel",
        data=analysis_file,
        file_name=f"דוח_פענוח_{employee}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

    st.divider()
    st.subheader("יצירה ישירה ביומן Google")
    if not oauth_dependencies_available():
        st.warning("חבילות Google Calendar אינן זמינות בסביבה הנוכחית.")
        return
    if not oauth_configured(st):
        st.warning("טרם הוגדרו פרטי Google OAuth ב-Streamlit Secrets. ניתן בינתיים להשתמש בקובץ ICS.")
        st.code(
            '[google_oauth]\nclient_id = "..."\nclient_secret = "..."\nredirect_uri = "https://YOUR-APP.streamlit.app"',
            language="toml",
        )
        return

    credentials = get_credentials(st)
    if credentials is None:
        st.link_button("התחברות מאובטחת ליומן Google", authorization_url(st), width="stretch")
        return

    service = build_service(credentials)
    try:
        calendars = list_writable_calendars(service)
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את רשימת היומנים: {exc}")
        return

    if not calendars:
        st.warning("לא נמצא יומן עם הרשאת כתיבה.")
        return
    selected_calendar = st.selectbox(
        "יומן יעד",
        calendars,
        format_func=lambda item: item["summary"] + (" (ראשי)" if item["primary"] else ""),
        key="target_calendar",
    )
    confirm = st.checkbox(f"בדקתי את {len(events)} האירועים ואני מאשר/ת ליצור אותם ביומן", key="confirm_calendar_write")
    col_create, col_disconnect = st.columns([3, 1])
    with col_create:
        if st.button("יצירת האירועים ביומן", type="primary", width="stretch", disabled=not confirm or not events):
            result = create_events(
                service,
                selected_calendar["id"],
                events,
                timezone_name=CONFIG.get("timezone", "Asia/Jerusalem"),
            )
            st.success(f"נוצרו {result['created']} אירועים. {result['existing']} אירועים כבר היו קיימים ולא נוצרו שוב.")
            for error in result["errors"]:
                st.error(error)
    with col_disconnect:
        if st.button("ניתוק היומן", width="stretch"):
            disconnect(st)
            st.rerun()


st.sidebar.title("כלי המערכת")
tool = st.sidebar.radio(
    "בחירת כלי",
    [
        "1. תכנון העדפות",
        "2. ריכוז ובניית לוז",
        "3. לוז סופי ויומן",
    ],
)
st.sidebar.markdown(
    '<div class="privacy"><b>פרטיות:</b> הקבצים מעובדים בזמן השימוש ואינם נשמרים על ידי קוד האפליקציה או במאגר GitHub. אין להעלות מידע רפואי מזהה.</div>',
    unsafe_allow_html=True,
)

if tool == "1. תכנון העדפות":
    tool_preferences()
elif tool == "2. ריכוז ובניית לוז":
    tool_manager()
else:
    tool_calendar()
