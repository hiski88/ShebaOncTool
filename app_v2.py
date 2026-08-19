from __future__ import annotations

import copy
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
    list_readable_calendars,
    list_writable_calendars,
    oauth_configured,
    oauth_dependencies_available,
    read_calendar_events,
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
    html, body, .stApp, [data-testid="stAppViewContainer"] { direction: rtl !important; text-align: right !important; }
    .main .block-container { max-width: 1500px; padding-top: 1.25rem; direction: rtl !important; }
    h1, h2, h3, p, label { text-align: right !important; }
    div[data-testid="stHorizontalBlock"] { direction: rtl !important; }
    section[data-testid="stSidebar"] { direction: rtl !important; text-align: right !important; }
    div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] { direction: rtl !important; text-align: right !important; }
    div[data-testid="stDataFrame"] [role="grid"], div[data-testid="stDataEditor"] [role="grid"] { direction: rtl !important; }
    div[data-testid="stDataFrame"] [role="columnheader"], div[data-testid="stDataFrame"] [role="gridcell"],
    div[data-testid="stDataEditor"] [role="columnheader"], div[data-testid="stDataEditor"] [role="gridcell"] {
        direction: rtl !important; text-align: right !important; justify-content: flex-end !important;
    }
    .hero { padding: 1.1rem 1.25rem; border: 1px solid #e6ebf2; border-radius: 18px; background: #fbfcff; margin-bottom: 1rem; }
    .hero h1 { margin: 0 0 .35rem 0; font-size: 1.9rem; }
    .hero p { margin: 0; color: #596579; }
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
        years = list(range(date.today().year - 1, date.today().year + 5))
        year = st.selectbox("שנה", years, index=years.index(default.year), key=f"{key}_year")
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
    st.markdown(f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def merge_event_maps(existing: dict[str, list[str]], new: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for key in set(existing) | set(new):
        merged[key] = list(dict.fromkeys([*existing.get(key, []), *new.get(key, [])]))
    return merged


def simple_preferences_text(employee: str, edited: pd.DataFrame) -> str:
    blocked: list[int] = []
    vacations: list[int] = []
    for _, row in edited.iterrows():
        day_number = pd.Timestamp(row["תאריך"]).day
        if bool(row.get("חסימה")):
            blocked.append(day_number)
        if bool(row.get("חופש")):
            vacations.append(day_number)
    return (
        f"{employee.strip()}\n"
        f"חסימות- {','.join(map(str, blocked))}\n"
        f"חופשים- {','.join(map(str, vacations))}"
    )


def render_calendar_reader(year: int, month: int) -> dict[str, list[str]]:
    st.subheader("אירועים מהיומנים האישיים")
    st.caption("אפשר לחבר עד שני יומנים. האירועים מוצגים לעזר בלבד ואינם מסמנים חסימה אוטומטית.")
    events_by_date = st.session_state.setdefault("preferences_calendar_events", {})

    if not oauth_dependencies_available():
        st.info("חיבור Google Calendar אינו זמין כרגע. ניתן להמשיך לתכנן ידנית.")
        return events_by_date
    if not oauth_configured(st):
        st.info("חיבור Google Calendar טרם הוגדר באפליקציה. ניתן להמשיך לתכנן ידנית.")
        return events_by_date

    credentials = get_credentials(st)
    if credentials is None:
        st.link_button("התחברות ל-Google Calendar", authorization_url(st), width="stretch")
        return events_by_date

    try:
        service = build_service(credentials)
        calendars = list_readable_calendars(service)
    except Exception as exc:
        st.warning(f"לא ניתן לקרוא את רשימת היומנים: {exc}")
        return events_by_date

    options = {item["label"]: item for item in calendars}
    labels = list(options)
    selected_labels = st.multiselect(
        "בחירת יומנים להצגה",
        labels,
        max_selections=2,
        help="ניתן לבחור יומן אחד או שניים. טעינה נוספת מצטרפת לאירועים שכבר נטענו.",
        key="preferences_calendar_selection",
    )

    col_load, col_clear, col_disconnect = st.columns([2, 1, 1])
    with col_load:
        if st.button("טען אירועים מהיומנים", type="primary", width="stretch"):
            if not selected_labels:
                st.warning("יש לבחור לפחות יומן אחד.")
            else:
                selected = [options[label] for label in selected_labels]
                try:
                    loaded = read_calendar_events(service, selected, year, month, CONFIG.get("timezone", "Asia/Jerusalem"))
                    st.session_state["preferences_calendar_events"] = merge_event_maps(events_by_date, loaded)
                    events_by_date = st.session_state["preferences_calendar_events"]
                    st.success("אירועי היומן נטענו לטבלת החודש.")
                except Exception as exc:
                    st.error(f"טעינת אירועי היומן נכשלה: {exc}")
    with col_clear:
        if st.button("נקה אירועים", width="stretch"):
            st.session_state["preferences_calendar_events"] = {}
            events_by_date = {}
            st.success("אירועי היומן נוקו.")
    with col_disconnect:
        if st.button("נתק יומן", width="stretch"):
            disconnect(st)
            st.info("החיבור נותק. האירועים שכבר נטענו נשארים בטבלה עד לניקוי שלהם.")

    return events_by_date


def event_dataframe(events) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "תאריך": event.event_date,
                "אירוע": event.title,
                "כל היום": event.all_day,
                "התחלה": "" if event.all_day or event.start is None else event.start.strftime("%d.%m.%Y %H:%M"),
                "סיום": "" if event.all_day or event.end is None else event.end.strftime("%d.%m.%Y %H:%M"),
                "קוד מטלה": event.task_code,
            }
            for event in events
        ]
    )


def tool_preferences() -> None:
    render_header(
        "1. תכנון העדפות אישיות",
        "מסמנים חסימות וחופש, רואים עד שני יומנים אישיים ומקבלים פלט פשוט להעברה.",
    )
    year, month = month_selector("preferences", offset=1)
    employee = st.text_input("שם עובד/ת", placeholder="שם מלא", key="preferences_employee")

    events_by_date = render_calendar_reader(year, month)

    table = build_month_table(year, month)
    table["אירועים מהיומן"] = table["תאריך"].map(
        lambda value: "\n".join(events_by_date.get(pd.Timestamp(value).date().isoformat(), []))
    )
    table["חסימה"] = False
    table["חופש"] = False
    table["הערה"] = ""

    edited = st.data_editor(
        table,
        width="stretch",
        hide_index=True,
        column_order=["הערה", "חופש", "חסימה", "אירועים מהיומן", "חג / יום מיוחד", "יום", "תאריך"],
        disabled=["תאריך", "יום", "חג / יום מיוחד", "אירועים מהיומן"],
        column_config={
            "תאריך": st.column_config.DateColumn("תאריך", format="DD.MM.YYYY"),
            "יום": st.column_config.TextColumn("יום"),
            "חג / יום מיוחד": st.column_config.TextColumn("חג / יום מיוחד"),
            "אירועים מהיומן": st.column_config.TextColumn("אירועים מהיומן", width="large"),
            "חסימה": st.column_config.CheckboxColumn("חסימה"),
            "חופש": st.column_config.CheckboxColumn("חופש"),
            "הערה": st.column_config.TextColumn("הערה", width="medium"),
        },
        key=f"preferences_table_{year}_{month}",
    )

    overlap = edited[edited["חסימה"] & edited["חופש"]]
    if not overlap.empty:
        st.warning("יש תאריכים שסומנו גם כחופש וגם כחסימה. המערכת תשמור את שני הסימונים.")

    if not employee.strip():
        st.info("לאחר הזנת שם, הפלט יופק אוטומטית.")
        return

    try:
        backend_edited = edited.rename(columns={"חסימה": "לא זמין"}).copy()
        payload = build_submission(employee, year, month, backend_edited)
        machine_output = encode_submission(payload)
        simple_output = simple_preferences_text(employee, edited)

        st.subheader("פלט פשוט להעברה")
        st.caption("זה הפלט שנוח להעתיק ולשלוח, בדומה לכלי של פנימית ד'.")
        st.text_area(
            "טקסט להעתקה",
            value=simple_output,
            height=110,
            key=f"preferences_simple_output_{year}_{month}_{employee}",
        )

        with st.expander("קוד מערכת למתכנן - מתקדם"):
            st.caption("אין צורך לקרוא או לערוך את הקוד. הוא מיועד לקליטה אוטומטית בכלי הריכוז.")
            st.text_area(
                "קוד לקליטה אוטומטית",
                value=machine_output,
                height=180,
                key=f"preferences_machine_output_{year}_{month}_{employee}",
            )

        workbook = build_personal_submission_workbook(employee, backend_edited, machine_output)
        st.download_button(
            "הורדת ההעדפות כקובץ Excel",
            data=workbook,
            file_name=f"העדפות_{employee}_{year}_{month:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    except Exception as exc:
        st.error(str(exc))


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

    st.info("בשלב הבא נפשט את איסוף התשובות. כרגע נשמר מנגנון הקובץ הקיים כדי לא לשבור את תהליך העבודה.")
    responses_file = st.file_uploader("העלאת קובץ ריכוז התשובות", type=["xlsx", "csv"], key="manager_responses")
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


CALENDAR_TASK_CODES = {
    "ward_duty_regular",
    "ward_duty_friday",
    "ward_duty_saturday",
    "er_duty",
    "day_hospital_duty",
    "vacation",
    "research",
    "study_day",
    "absence",
    "absence_other",
    "shahar_program",
}


def calendar_candidate_events(records: pd.DataFrame, employee: str):
    selected = records[(records["employee"] == employee) & (records["task_code"].isin(CALENDAR_TASK_CODES))].copy()
    event_config = copy.deepcopy(CONFIG)
    for code in {"vacation", "research", "study_day", "absence", "absence_other", "shahar_program"}:
        event_config.setdefault("event_defaults", {}).setdefault(code, {"all_day": True})["create"] = True
        event_config["event_defaults"][code].setdefault("all_day", True)
    events = records_to_events(selected, employee, event_config)
    return selected, events, event_config


def tool_calendar() -> None:
    render_header(
        "3. לוז סופי ושמירה ביומן",
        "שומרים ביומן רק תורנויות ואירועים מיוחדים, לא ימי עבודה שגרתיים במחלקה.",
    )
    uploaded = st.file_uploader("העלאת לוז סופי", type=["xls", "xlsx", "xlsm"], key="final_schedule")
    if uploaded is None:
        st.info("המערכת תומכת ב-XLS וב-XLSX. ב-XLSX זיהוי עיצובי מחיקה אמין יותר.")
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
    names = sorted(set(inferred + [line.strip() for line in additional.splitlines() if line.strip()]))
    if not names:
        st.warning("לא זוהו שמות. יש להזין לפחות שם אחד בשדה התיקון.")
        return

    employee = st.selectbox("בחירת עובד/ת", names, key="calendar_employee")
    try:
        records = parse_schedule(workbook, CONFIG, names)
    except Exception as exc:
        st.error(f"פענוח הלוז נכשל: {exc}")
        return

    employee_records = records[records["employee"] == employee].copy()
    summary = summarize_schedule(records)
    validation = validate_schedule(records, CONFIG)
    candidate_records, events, event_config = calendar_candidate_events(records, employee)

    st.subheader(f"אירועים מיוחדים שזוהו עבור {employee}")
    st.caption("שם מחוק עם חופש, מחקר או סטטוס מיוחד נשמר כרשומה של העובד ויכול להופיע כאן כאירוע לבחירה.")
    if candidate_records.empty:
        st.warning("לא נמצאו תורנויות או אירועים מיוחדים עבור העובד/ת שנבחר/ה.")
    else:
        display = candidate_records[["date", "day", "task_label", "subtype", "raw_text"]].rename(
            columns={"date": "תאריך", "day": "יום", "task_label": "אירוע", "subtype": "פירוט", "raw_text": "מקור"}
        )
        st.dataframe(display, width="stretch", hide_index=True)

    st.subheader("אירועים מוצעים ליומן")
    if not events:
        st.info("אין כרגע אירועים לשמירה ביומן.")
        selected_events = []
        event_table = pd.DataFrame()
    else:
        event_table = event_dataframe(events)
        preview = event_table.copy()
        preview.insert(0, "להוסיף ליומן", True)
        edited_preview = st.data_editor(
            preview,
            hide_index=True,
            width="stretch",
            column_order=["קוד מטלה", "סיום", "התחלה", "כל היום", "אירוע", "תאריך", "להוסיף ליומן"],
            disabled=[column for column in preview.columns if column != "להוסיף ליומן"],
            column_config={"להוסיף ליומן": st.column_config.CheckboxColumn("להוסיף ליומן")},
            key=f"calendar_event_selection_{employee}",
        )
        selected_events = [event for event, keep in zip(events, edited_preview["להוסיף ליומן"].tolist()) if bool(keep)]
        st.caption(f"נבחרו {len(selected_events)} מתוך {len(events)} אירועים.")

    ics = events_to_ics(selected_events, event_config.get("timezone", "Asia/Jerusalem"))
    st.download_button(
        "הורדת קובץ ICS",
        data=ics,
        file_name=f"לוז_{employee}.ics",
        mime="text/calendar",
        width="stretch",
        disabled=not selected_events,
    )

    with st.expander("סיכום ובדיקות למתכנן"):
        st.subheader("סיכום מטלות אוטומטי")
        st.dataframe(summary, width="stretch", hide_index=True)
        st.subheader("בדיקות איוש אוטומטיות")
        if validation.empty:
            st.success("לא נמצאו חריגות לפי כללי האיוש שהוגדרו.")
        else:
            st.warning(f"נמצאו {len(validation)} חריגות לבדיקה לפני פרסום הלוז.")
            st.dataframe(validation, width="stretch", hide_index=True)
        analysis_file = build_schedule_analysis_workbook(employee_records, summary, event_table, validation)
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
    confirm = st.checkbox(
        f"בדקתי את {len(selected_events)} האירועים ואני מאשר/ת ליצור אותם ביומן",
        key="confirm_calendar_write",
    )
    col_create, col_disconnect = st.columns([3, 1])
    with col_create:
        if st.button("יצירת האירועים ביומן", type="primary", width="stretch", disabled=not confirm or not selected_events):
            result = create_events(
                service,
                selected_calendar["id"],
                selected_events,
                timezone_name=CONFIG.get("timezone", "Asia/Jerusalem"),
            )
            st.success(f"נוצרו {result['created']} אירועים. {result['existing']} אירועים כבר היו קיימים ולא נוצרו שוב.")
            for error in result["errors"]:
                st.error(error)
    with col_disconnect:
        if st.button("ניתוק היומן", width="stretch", key="calendar_write_disconnect"):
            disconnect(st)
            st.rerun()


def main() -> None:
    st.sidebar.title("כלי המערכת")
    tool = st.sidebar.radio(
        "בחירת כלי",
        ["1. תכנון העדפות", "2. ריכוז ובניית לוז", "3. לוז סופי ויומן"],
    )

    if tool == "1. תכנון העדפות":
        tool_preferences()
    elif tool == "2. ריכוז ובניית לוז":
        tool_manager()
    else:
        tool_calendar()


if __name__ == "__main__":
    main()
