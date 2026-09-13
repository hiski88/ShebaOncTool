"""Tool 6 - worker administration."""
from __future__ import annotations

import re

from google_sheets_submissions import _service


WORKERS_SHEET = "Workers"
MARITAL_STATUS_OPTIONS = [
    "רווק/ה",
    "בזוגיות / ידוע/ה בציבור",
    "נשוי/אה",
    "פרוד/ה",
    "גרוש/ה",
    "אלמן/ה",
    "אחר",
    "מעדיף/ה לא לציין",
]
CHILDREN_OPTIONS = ["0", "1", "2", "3", "4", "5", "6", "7+"]
TRACK_OPTIONS = ["אונקולוגיה רפואית", "רדיותרפיה"]
STATUS_OPTIONS = ["פעיל", "לא פעיל"]
ELIGIBILITY_OPTIONS = [
    "לא כשיר לתורנויות",
    "מחלקה",
    "מחלקה + אשפוז יום",
    "מחלקה + אשפוז יום + מיון",
]
YES_NO_OPTIONS = ["לא", "כן"]


def _workers_service(st):
    service, spreadsheet_id, _ = _service(st)
    return service, spreadsheet_id


def _read_worker_rows(st) -> list[list[str]]:
    service, spreadsheet_id = _workers_service(st)
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{WORKERS_SHEET}'!A2:S500",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    return response.get("values", [])


def _next_worker_id(rows: list[list[str]]) -> str:
    highest = 0
    for row in rows:
        if not row:
            continue
        value = str(row[0]).strip().upper()
        match = re.fullmatch(r"W(\d+)", value)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"W{highest + 1:04d}"


def _append_worker(st, values: list[str]) -> None:
    service, spreadsheet_id = _workers_service(st)
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{WORKERS_SHEET}'!A:S",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [values]},
    ).execute()


def _render_add_worker(st) -> None:
    st.subheader("הוספת עובד/ת")
    st.caption("כל השדות במסך זה הם שדות חובה. מזהה העובד נוצר אוטומטית ואינו דורש הזנה.")

    with st.form("tool6_add_worker_form", clear_on_submit=False):
        st.markdown("### פרטים אישיים")

        row1_col1, row1_col2 = st.columns(2)
        with row1_col1:
            first_name = st.text_input("שם פרטי")
        with row1_col2:
            last_name = st.text_input("שם משפחה")

        row2_col1, row2_col2 = st.columns(2)
        with row2_col1:
            id_number = st.text_input("ת.ז")
        with row2_col2:
            birth_date = st.date_input("תאריך לידה", value=None, format="DD/MM/YYYY")

        row3_col1, row3_col2 = st.columns(2)
        with row3_col1:
            address = st.text_input("כתובת")
        with row3_col2:
            locality = st.text_input("יישוב מגורים")

        row4_col1, row4_col2 = st.columns(2)
        with row4_col1:
            phone = st.text_input("טלפון")
        with row4_col2:
            email = st.text_input("אימייל")

        row5_col1, row5_col2 = st.columns(2)
        with row5_col1:
            marital_status = st.selectbox("מצב משפחתי", MARITAL_STATUS_OPTIONS)
        with row5_col2:
            children = st.selectbox("מספר ילדים", CHILDREN_OPTIONS)

        st.markdown("### פרטים מקצועיים")

        row6_col1, row6_col2 = st.columns(2)
        with row6_col1:
            track = st.selectbox("מסלול / התמחות", TRACK_OPTIONS)
        with row6_col2:
            status = st.selectbox("סטטוס", STATUS_OPTIONS)

        row7_col1, row7_col2 = st.columns(2)
        with row7_col1:
            eligibility = st.selectbox("כשירות תורנויות", ELIGIBILITY_OPTIONS)
        with row7_col2:
            basic_science_exemption = st.selectbox("פטור מדעי יסוד", YES_NO_OPTIONS)

        row8_col1, row8_col2 = st.columns(2)
        with row8_col1:
            department_start = st.date_input(
                "תאריך תחילת פעילות במחלקה",
                value=None,
                format="DD/MM/YYYY",
            )
        with row8_col2:
            specialization_start = st.date_input(
                "תאריך תחילת התמחות",
                value=None,
                format="DD/MM/YYYY",
            )

        general_note = st.text_area("הערה כללית")
        submitted = st.form_submit_button("הוסף עובד/ת", type="primary", use_container_width=True)

    if not submitted:
        return

    required_text = {
        "שם פרטי": first_name,
        "שם משפחה": last_name,
        "ת.ז": id_number,
        "כתובת": address,
        "יישוב מגורים": locality,
        "טלפון": phone,
        "אימייל": email,
        "הערה כללית": general_note,
    }
    missing = [label for label, value in required_text.items() if not str(value or "").strip()]
    if birth_date is None:
        missing.append("תאריך לידה")
    if department_start is None:
        missing.append("תאריך תחילת פעילות במחלקה")
    if specialization_start is None:
        missing.append("תאריך תחילת התמחות")

    if missing:
        st.error("יש למלא את כל שדות החובה: " + ", ".join(missing))
        return

    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
        st.error("כתובת האימייל אינה בפורמט תקין.")
        return

    try:
        existing_rows = _read_worker_rows(st)
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את רשימת העובדים: {exc}")
        return

    normalized_id = id_number.strip()
    for row in existing_rows:
        if len(row) > 3 and str(row[3]).strip() == normalized_id:
            st.error("כבר קיים עובד/ת עם מספר ת.ז זה.")
            return

    worker_id = _next_worker_id(existing_rows)
    values = [
        worker_id,
        first_name.strip(),
        last_name.strip(),
        normalized_id,
        birth_date.strftime("%d/%m/%Y"),
        address.strip(),
        locality.strip(),
        phone.strip(),
        email.strip(),
        marital_status,
        children,
        track,
        status,
        eligibility,
        basic_science_exemption,
        department_start.strftime("%d/%m/%Y"),
        "",  # תאריך סיום פעילות - לא נקבע בעת הוספת עובד חדש
        general_note.strip(),
        specialization_start.strftime("%d/%m/%Y"),
    ]

    try:
        _append_worker(st, values)
    except Exception as exc:
        st.error(f"שמירת העובד/ת נכשלה: {exc}")
        return

    st.success(f"העובד/ת {first_name.strip()} {last_name.strip()} נוסף/ה בהצלחה.")
    st.caption(f"מזהה פנימי: {worker_id}")


def render(app_module) -> None:
    st = app_module.st
    app_module.render_header(
        "6. ניהול עובדים",
        "ניהול מצבת עובדים, פרטים תעסוקתיים ותקופות התמחות.",
    )

    action = st.radio(
        "בחירת פעולה",
        [
            "הוספת עובד/ת",
            "עריכת עובד/ת",
            "צפייה ברשימת עובדים",
            "ניהול התמחות ותקופות",
        ],
        key="tool6_action",
    )

    st.divider()
    if action == "הוספת עובד/ת":
        _render_add_worker(st)
        return

    st.info(f"המסך '{action}' ייבנה בשלב הבא.")
