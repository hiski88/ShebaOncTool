"""Tool 6 - worker administration."""
from __future__ import annotations

from datetime import date, datetime
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

from google_sheets_submissions import _service


WORKERS_SHEET = "Workers"
WORKER_PERIODS_SHEET = "WorkerPeriods"
SELECT_PLACEHOLDER = "בחר/י..."
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
PERIOD_TYPE_OPTIONS = [
    "פנימית",
    "מחלקה",
    "אשפוז יום",
    "רדיותרפיה",
    "מיון",
    "מרפאות",
    "אבחון מהיר",
    "מחקר",
    "מדעי יסוד",
    "הכנה לשלב א'",
    "הכנה לשלב ב'",
    "חופשה",
    "מילואים",
    "חופשת לידה",
    "מחלה ממושכת",
    "אחר",
]


def _workers_service(st):
    service, spreadsheet_id, _ = _service(st)
    return service, spreadsheet_id


def _read_worker_rows(st) -> list[list[str]]:
    service, spreadsheet_id = _workers_service(st)
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{WORKERS_SHEET}'!A2:S",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    return response.get("values", [])


def _read_period_rows(st) -> list[list[str]]:
    service, spreadsheet_id = _workers_service(st)
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{WORKER_PERIODS_SHEET}'!A2:J",
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


def _new_period_id() -> str:
    """Generate a stable period identity without relying on row position."""
    return f"P{uuid4().hex[:10].upper()}"


def _now_text() -> str:
    return datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%d/%m/%Y %H:%M:%S")


def _append_worker(st, values: list[str]) -> None:
    service, spreadsheet_id = _workers_service(st)
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{WORKERS_SHEET}'!A:S",
        valueInputOption="USER_ENTERED",
        # Use the next existing grid row instead of inserting a fresh unformatted
        # row. This preserves the date/text formats prepared in the Workers tab.
        insertDataOption="OVERWRITE",
        body={"values": [values]},
    ).execute()


def _append_period(st, values: list[str]) -> None:
    service, spreadsheet_id = _workers_service(st)
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{WORKER_PERIODS_SHEET}'!A:J",
        valueInputOption="USER_ENTERED",
        insertDataOption="OVERWRITE",
        body={"values": [values]},
    ).execute()


def _update_worker_row(st, row_number: int, values: list[str]) -> None:
    """Update the exact Workers row while preserving its existing formatting."""
    service, spreadsheet_id = _workers_service(st)
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{WORKERS_SHEET}'!A{row_number}:S{row_number}",
        valueInputOption="USER_ENTERED",
        body={"values": [values]},
    ).execute()


def _update_period_row(st, row_number: int, values: list[str]) -> None:
    """Update the exact WorkerPeriods row; Period ID and Worker ID stay stable."""
    service, spreadsheet_id = _workers_service(st)
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{WORKER_PERIODS_SHEET}'!A{row_number}:J{row_number}",
        valueInputOption="USER_ENTERED",
        body={"values": [values]},
    ).execute()


def _update_worker_status(st, row_number: int, status: str) -> None:
    service, spreadsheet_id = _workers_service(st)
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{WORKERS_SHEET}'!M{row_number}",
        valueInputOption="RAW",
        body={"values": [[status]]},
    ).execute()


def _required_selectbox(st, label: str, options: list[str]):
    return st.selectbox(label, [SELECT_PLACEHOLDER, *options])


def _parse_sheet_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _format_date(value: object) -> str:
    parsed = value if isinstance(value, date) else _parse_sheet_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else ""


def _option_list(options: list[str], current: str) -> list[str]:
    """Keep unexpected legacy values selectable so editing never erases them."""
    value = str(current or "").strip()
    if value and value not in options:
        return [value, *options]
    return list(options)


def _worker_records(rows: list[list[str]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for offset, raw in enumerate(rows, start=2):
        row = [str(item) for item in raw] + [""] * (19 - len(raw))
        worker_id = row[0].strip()
        if not worker_id:
            continue
        records.append(
            {
                "row_number": offset,
                "worker_id": worker_id,
                "first_name": row[1].strip(),
                "last_name": row[2].strip(),
                "id_number": row[3].strip(),
                "birth_date": _parse_sheet_date(row[4]),
                "address": row[5].strip(),
                "locality": row[6].strip(),
                "phone": row[7].strip(),
                "email": row[8].strip(),
                "marital_status": row[9].strip(),
                "children": row[10].strip(),
                "track": row[11].strip(),
                "status": row[12].strip(),
                "eligibility": row[13].strip(),
                "basic_science_exemption": row[14].strip(),
                "department_start": _parse_sheet_date(row[15]),
                "activity_end": _parse_sheet_date(row[16]),
                "general_note": row[17].strip(),
                "specialization_start": _parse_sheet_date(row[18]),
            }
        )
    return records


def _period_records(rows: list[list[str]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for offset, raw in enumerate(rows, start=2):
        row = [str(item) for item in raw] + [""] * (10 - len(raw))
        period_id = row[0].strip()
        worker_id = row[1].strip()
        if not period_id or not worker_id:
            continue
        records.append(
            {
                "row_number": offset,
                "period_id": period_id,
                "worker_id": worker_id,
                "period_type": row[2].strip(),
                "framework": row[3].strip(),
                "subunit": row[4].strip(),
                "location": row[5].strip(),
                "start_date": _parse_sheet_date(row[6]),
                "end_date": _parse_sheet_date(row[7]),
                "note": row[8].strip(),
                "updated_at": row[9].strip(),
            }
        )
    return records


def _validate_worker_fields(
    *,
    first_name: str,
    last_name: str,
    id_number: str,
    birth_date: date | None,
    address: str,
    locality: str,
    phone: str,
    email: str,
    marital_status: str,
    children: str,
    track: str,
    status: str,
    eligibility: str,
    basic_science_exemption: str,
    department_start: date | None,
    specialization_start: date | None,
    activity_end: date | None = None,
) -> str | None:
    required_text = {
        "שם פרטי": first_name,
        "שם משפחה": last_name,
        "ת.ז": id_number,
        "כתובת": address,
        "יישוב מגורים": locality,
        "טלפון": phone,
        "אימייל": email,
    }
    missing = [label for label, value in required_text.items() if not str(value or "").strip()]
    required_selections = {
        "מצב משפחתי": marital_status,
        "מספר ילדים": children,
        "מסלול / התמחות": track,
        "סטטוס": status,
        "כשירות תורנויות": eligibility,
        "פטור מדעי יסוד": basic_science_exemption,
    }
    missing.extend(
        label
        for label, value in required_selections.items()
        if not str(value or "").strip() or value == SELECT_PLACEHOLDER
    )
    if birth_date is None:
        missing.append("תאריך לידה")
    if department_start is None:
        missing.append("תאריך תחילת פעילות במחלקה")
    if specialization_start is None:
        missing.append("תאריך תחילת התמחות")
    if missing:
        return "יש למלא את כל שדות החובה: " + ", ".join(missing)

    if department_start < birth_date:
        return "תאריך תחילת הפעילות במחלקה לא יכול להיות מוקדם מתאריך הלידה."
    if specialization_start < birth_date:
        return "תאריך תחילת ההתמחות לא יכול להיות מוקדם מתאריך הלידה."
    if activity_end is not None and activity_end < department_start:
        return "תאריך סיום הפעילות לא יכול להיות מוקדם מתאריך תחילת הפעילות במחלקה."
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email.strip()):
        return "כתובת האימייל אינה בפורמט תקין."
    return None


def _validate_period_fields(
    *,
    period_type: str,
    start_date: date | None,
    end_date: date | None,
) -> str | None:
    if not str(period_type or "").strip() or period_type == SELECT_PLACEHOLDER:
        return "יש לבחור סוג תקופה."
    if start_date is None:
        return "יש להזין תאריך התחלה."
    if end_date is None:
        return "יש להזין תאריך סיום."
    if end_date < start_date:
        return "תאריך הסיום לא יכול להיות מוקדם מתאריך ההתחלה."
    return None


def _worker_label(worker: dict[str, object], include_status: bool = True) -> str:
    full_name = " ".join(
        part for part in (str(worker.get("first_name", "")), str(worker.get("last_name", ""))) if part
    ).strip()
    parts = [full_name, str(worker.get("track", ""))]
    if include_status:
        parts.append(str(worker.get("status", "")))
    return " - ".join(part for part in parts if part)


def _render_add_worker(st) -> None:
    st.subheader("הוספת עובד/ת")
    st.caption(
        "כל השדות במסך זה, למעט הערה כללית, הם שדות חובה. "
        "מזהה העובד נוצר אוטומטית ואינו דורש הזנה."
    )

    today = date.today()
    earliest_birth_date = date(today.year - 70, 1, 1)

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
            birth_date = st.date_input(
                "תאריך לידה",
                value=None,
                min_value=earliest_birth_date,
                max_value=today,
                format="DD/MM/YYYY",
            )

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
            marital_status = _required_selectbox(st, "מצב משפחתי", MARITAL_STATUS_OPTIONS)
        with row5_col2:
            children = _required_selectbox(st, "מספר ילדים", CHILDREN_OPTIONS)

        st.markdown("### פרטים מקצועיים")

        row6_col1, row6_col2 = st.columns(2)
        with row6_col1:
            track = _required_selectbox(st, "מסלול / התמחות", TRACK_OPTIONS)
        with row6_col2:
            status = _required_selectbox(st, "סטטוס", STATUS_OPTIONS)

        row7_col1, row7_col2 = st.columns(2)
        with row7_col1:
            eligibility = _required_selectbox(st, "כשירות תורנויות", ELIGIBILITY_OPTIONS)
        with row7_col2:
            basic_science_exemption = _required_selectbox(st, "פטור מדעי יסוד", YES_NO_OPTIONS)

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

        general_note = st.text_area("הערה כללית (אופציונלי)")
        submitted = st.form_submit_button("הוסף עובד/ת", type="primary", use_container_width=True)

    if not submitted:
        return

    validation_error = _validate_worker_fields(
        first_name=first_name,
        last_name=last_name,
        id_number=id_number,
        birth_date=birth_date,
        address=address,
        locality=locality,
        phone=phone,
        email=email,
        marital_status=marital_status,
        children=children,
        track=track,
        status=status,
        eligibility=eligibility,
        basic_science_exemption=basic_science_exemption,
        department_start=department_start,
        specialization_start=specialization_start,
    )
    if validation_error:
        st.error(validation_error)
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


def _render_edit_worker(st) -> None:
    st.subheader("עריכת עובד/ת")
    st.caption("בחר/י עובד/ת, עדכן/י את הפרטים ושמור/י. מזהה העובד הפנימי אינו משתנה.")

    try:
        rows = _read_worker_rows(st)
        workers = _worker_records(rows)
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את רשימת העובדים: {exc}")
        return

    if not workers:
        st.info("עדיין אין עובדים במערכת.")
        return

    labels: list[str] = []
    workers_by_label: dict[str, dict[str, object]] = {}
    for worker in workers:
        label = _worker_label(worker)
        if label in workers_by_label:
            label = f"{label} - {worker['worker_id']}"
        labels.append(label)
        workers_by_label[label] = worker

    selected_label = st.selectbox("עובד/ת", labels, key="tool6_edit_worker_select")
    selected = workers_by_label[selected_label]
    worker_id = str(selected["worker_id"])
    row_number = int(selected["row_number"])

    st.caption(f"מזהה פנימי: {worker_id}")

    today = date.today()
    earliest_birth_date = date(today.year - 70, 1, 1)
    birth_default = selected.get("birth_date")
    if birth_default is not None and birth_default < earliest_birth_date:
        earliest_birth_date = birth_default

    marital_options = _option_list(MARITAL_STATUS_OPTIONS, str(selected["marital_status"]))
    children_options = _option_list(CHILDREN_OPTIONS, str(selected["children"]))
    track_options = _option_list(TRACK_OPTIONS, str(selected["track"]))
    status_options = _option_list(STATUS_OPTIONS, str(selected["status"]))
    eligibility_options = _option_list(ELIGIBILITY_OPTIONS, str(selected["eligibility"]))
    science_options = _option_list(YES_NO_OPTIONS, str(selected["basic_science_exemption"]))

    with st.form(f"tool6_edit_worker_form_{worker_id}", clear_on_submit=False):
        st.markdown("### פרטים אישיים")
        row1_col1, row1_col2 = st.columns(2)
        with row1_col1:
            first_name = st.text_input(
                "שם פרטי", value=str(selected["first_name"]), key=f"tool6_edit_first_{worker_id}"
            )
        with row1_col2:
            last_name = st.text_input(
                "שם משפחה", value=str(selected["last_name"]), key=f"tool6_edit_last_{worker_id}"
            )

        row2_col1, row2_col2 = st.columns(2)
        with row2_col1:
            id_number = st.text_input(
                "ת.ז", value=str(selected["id_number"]), key=f"tool6_edit_id_{worker_id}"
            )
        with row2_col2:
            birth_date = st.date_input(
                "תאריך לידה",
                value=selected.get("birth_date"),
                min_value=earliest_birth_date,
                max_value=today,
                format="DD/MM/YYYY",
                key=f"tool6_edit_birth_{worker_id}",
            )

        row3_col1, row3_col2 = st.columns(2)
        with row3_col1:
            address = st.text_input(
                "כתובת", value=str(selected["address"]), key=f"tool6_edit_address_{worker_id}"
            )
        with row3_col2:
            locality = st.text_input(
                "יישוב מגורים", value=str(selected["locality"]), key=f"tool6_edit_locality_{worker_id}"
            )

        row4_col1, row4_col2 = st.columns(2)
        with row4_col1:
            phone = st.text_input(
                "טלפון", value=str(selected["phone"]), key=f"tool6_edit_phone_{worker_id}"
            )
        with row4_col2:
            email = st.text_input(
                "אימייל", value=str(selected["email"]), key=f"tool6_edit_email_{worker_id}"
            )

        row5_col1, row5_col2 = st.columns(2)
        with row5_col1:
            current_marital = str(selected["marital_status"])
            marital_status = st.selectbox(
                "מצב משפחתי",
                marital_options,
                index=marital_options.index(current_marital) if current_marital in marital_options else 0,
                key=f"tool6_edit_marital_{worker_id}",
            )
        with row5_col2:
            current_children = str(selected["children"])
            children = st.selectbox(
                "מספר ילדים",
                children_options,
                index=children_options.index(current_children) if current_children in children_options else 0,
                key=f"tool6_edit_children_{worker_id}",
            )

        st.markdown("### פרטים מקצועיים")
        row6_col1, row6_col2 = st.columns(2)
        with row6_col1:
            current_track = str(selected["track"])
            track = st.selectbox(
                "מסלול / התמחות",
                track_options,
                index=track_options.index(current_track) if current_track in track_options else 0,
                key=f"tool6_edit_track_{worker_id}",
            )
        with row6_col2:
            current_status = str(selected["status"])
            status = st.selectbox(
                "סטטוס",
                status_options,
                index=status_options.index(current_status) if current_status in status_options else 0,
                key=f"tool6_edit_status_{worker_id}",
            )

        row7_col1, row7_col2 = st.columns(2)
        with row7_col1:
            current_eligibility = str(selected["eligibility"])
            eligibility = st.selectbox(
                "כשירות תורנויות",
                eligibility_options,
                index=eligibility_options.index(current_eligibility) if current_eligibility in eligibility_options else 0,
                key=f"tool6_edit_eligibility_{worker_id}",
            )
        with row7_col2:
            current_science = str(selected["basic_science_exemption"])
            basic_science_exemption = st.selectbox(
                "פטור מדעי יסוד",
                science_options,
                index=science_options.index(current_science) if current_science in science_options else 0,
                key=f"tool6_edit_science_{worker_id}",
            )

        row8_col1, row8_col2 = st.columns(2)
        with row8_col1:
            department_start = st.date_input(
                "תאריך תחילת פעילות במחלקה",
                value=selected.get("department_start"),
                format="DD/MM/YYYY",
                key=f"tool6_edit_department_start_{worker_id}",
            )
        with row8_col2:
            specialization_start = st.date_input(
                "תאריך תחילת התמחות",
                value=selected.get("specialization_start"),
                format="DD/MM/YYYY",
                key=f"tool6_edit_specialization_start_{worker_id}",
            )

        activity_end = st.date_input(
            "תאריך סיום פעילות (אופציונלי)",
            value=selected.get("activity_end"),
            format="DD/MM/YYYY",
            key=f"tool6_edit_activity_end_{worker_id}",
        )
        general_note = st.text_area(
            "הערה כללית (אופציונלי)",
            value=str(selected["general_note"]),
            key=f"tool6_edit_note_{worker_id}",
        )
        save_clicked = st.form_submit_button(
            "שמור שינויים", type="primary", use_container_width=True
        )

    if save_clicked:
        validation_error = _validate_worker_fields(
            first_name=first_name,
            last_name=last_name,
            id_number=id_number,
            birth_date=birth_date,
            address=address,
            locality=locality,
            phone=phone,
            email=email,
            marital_status=marital_status,
            children=children,
            track=track,
            status=status,
            eligibility=eligibility,
            basic_science_exemption=basic_science_exemption,
            department_start=department_start,
            specialization_start=specialization_start,
            activity_end=activity_end,
        )
        if validation_error:
            st.error(validation_error)
            return

        normalized_id = str(id_number or "").strip()
        for other in workers:
            if str(other["worker_id"]) == worker_id:
                continue
            if str(other["id_number"]).strip() == normalized_id:
                st.error("כבר קיים עובד/ת אחר/ת עם מספר ת.ז זה.")
                return

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
            activity_end.strftime("%d/%m/%Y") if activity_end else "",
            general_note.strip(),
            specialization_start.strftime("%d/%m/%Y"),
        ]
        try:
            _update_worker_row(st, row_number, values)
        except Exception as exc:
            st.error(f"עדכון העובד/ת נכשל: {exc}")
            return
        st.success("פרטי העובד/ת עודכנו בהצלחה.")
        st.rerun()

    st.divider()
    current_status = str(selected["status"])
    if current_status == "פעיל":
        if st.button(
            "סמן/י כלא פעיל/ה", width="stretch", key=f"tool6_mark_inactive_{worker_id}"
        ):
            try:
                _update_worker_status(st, row_number, "לא פעיל")
            except Exception as exc:
                st.error(f"שינוי הסטטוס נכשל: {exc}")
                return
            st.success("העובד/ת סומן/ה כלא פעיל/ה.")
            st.rerun()
    else:
        if st.button(
            "החזר/י לפעיל/ה", width="stretch", key=f"tool6_mark_active_{worker_id}"
        ):
            try:
                _update_worker_status(st, row_number, "פעיל")
            except Exception as exc:
                st.error(f"שינוי הסטטוס נכשל: {exc}")
                return
            st.success("העובד/ת הוחזר/ה לסטטוס פעיל.")
            st.rerun()


def _render_worker_list(st, pd_module) -> None:
    st.subheader("רשימת עובדים")
    st.caption("הרשימה מציגה מידע תפעולי בלבד ואינה חושפת ת.ז, כתובת או מידע משפחתי.")

    try:
        workers = _worker_records(_read_worker_rows(st))
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את רשימת העובדים: {exc}")
        return

    if not workers:
        st.info("עדיין אין עובדים במערכת.")
        return

    filter_name_col, filter_status_col, filter_track_col = st.columns(3)
    with filter_name_col:
        name_query = st.text_input("חיפוש לפי שם", key="tool6_list_name_filter")
    with filter_status_col:
        status_filter = st.selectbox(
            "סטטוס", ["הכל", *STATUS_OPTIONS], key="tool6_list_status_filter"
        )
    with filter_track_col:
        track_filter = st.selectbox(
            "מסלול", ["הכל", *TRACK_OPTIONS], key="tool6_list_track_filter"
        )

    query = str(name_query or "").strip().casefold()
    filtered: list[dict[str, object]] = []
    for worker in workers:
        full_name = " ".join(
            part for part in (str(worker["first_name"]), str(worker["last_name"])) if part
        ).strip()
        if query and query not in full_name.casefold():
            continue
        if status_filter != "הכל" and str(worker["status"]) != status_filter:
            continue
        if track_filter != "הכל" and str(worker["track"]) != track_filter:
            continue
        filtered.append(worker)

    filtered.sort(
        key=lambda item: (
            0 if str(item.get("status", "")) == "פעיל" else 1,
            str(item.get("last_name", "")).casefold(),
            str(item.get("first_name", "")).casefold(),
        )
    )

    st.caption(f"מציג {len(filtered)} מתוך {len(workers)} עובדים.")
    if not filtered:
        st.info("לא נמצאו עובדים התואמים לסינון.")
        return

    visible_rows = []
    for worker in filtered:
        visible_rows.append(
            {
                "שם מלא": " ".join(
                    part for part in (str(worker["first_name"]), str(worker["last_name"])) if part
                ).strip(),
                "טלפון": str(worker["phone"]),
                "אימייל": str(worker["email"]),
                "מסלול": str(worker["track"]),
                "סטטוס": str(worker["status"]),
                "כשירות תורנויות": str(worker["eligibility"]),
                "תחילת פעילות": _format_date(worker.get("department_start")),
                "תחילת התמחות": _format_date(worker.get("specialization_start")),
            }
        )

    st.dataframe(pd_module.DataFrame(visible_rows), width="stretch", hide_index=True)


def _render_periods(st, pd_module) -> None:
    st.subheader("ניהול התמחות ותקופות")
    st.caption(
        "WorkerPeriods היא מקור האמת לתקופות מדויקות. ניתן להוסיף ולעדכן תקופות; "
        "חפיפות מותרות כאשר הן משקפות את המציאות."
    )

    try:
        workers = _worker_records(_read_worker_rows(st))
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את רשימת העובדים: {exc}")
        return

    if not workers:
        st.info("יש להוסיף עובד/ת לפני ניהול תקופות.")
        return

    labels: list[str] = []
    workers_by_label: dict[str, dict[str, object]] = {}
    for worker in workers:
        label = _worker_label(worker)
        if label in workers_by_label:
            label = f"{label} - {worker['worker_id']}"
        labels.append(label)
        workers_by_label[label] = worker

    selected_label = st.selectbox("עובד/ת", labels, key="tool6_period_worker_select")
    selected_worker = workers_by_label[selected_label]
    worker_id = str(selected_worker["worker_id"])

    try:
        all_periods = _period_records(_read_period_rows(st))
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את התקופות: {exc}")
        return

    worker_periods = [item for item in all_periods if str(item["worker_id"]) == worker_id]
    worker_periods.sort(
        key=lambda item: (
            item.get("start_date") or date.min,
            item.get("end_date") or date.min,
            str(item.get("period_type", "")),
        )
    )

    st.markdown("### תקופות קיימות")
    if worker_periods:
        visible = [
            {
                "סוג תקופה": str(item["period_type"]),
                "מסגרת / מחלקה": str(item["framework"]),
                "תת-יחידה / רוטציה": str(item["subunit"]),
                "מקום": str(item["location"]),
                "תאריך התחלה": _format_date(item.get("start_date")),
                "תאריך סיום": _format_date(item.get("end_date")),
                "הערה": str(item["note"]),
                "עודכן לאחרונה": str(item["updated_at"]),
            }
            for item in worker_periods
        ]
        st.dataframe(pd_module.DataFrame(visible), width="stretch", hide_index=True)
    else:
        st.info("עדיין לא הוגדרו תקופות לעובד/ת זה/ו.")

    st.divider()
    period_action = st.radio(
        "פעולה",
        ["הוספת תקופה", "עריכת תקופה קיימת"],
        horizontal=True,
        key="tool6_period_action",
    )

    if period_action == "הוספת תקופה":
        with st.form(f"tool6_add_period_form_{worker_id}", clear_on_submit=False):
            period_type = _required_selectbox(st, "סוג תקופה", PERIOD_TYPE_OPTIONS)
            row1_col1, row1_col2 = st.columns(2)
            with row1_col1:
                framework = st.text_input("מסגרת / מחלקה (אופציונלי)")
            with row1_col2:
                subunit = st.text_input("תת-יחידה / רוטציה (אופציונלי)")
            location = st.text_input("מקום (אופציונלי)")
            row2_col1, row2_col2 = st.columns(2)
            with row2_col1:
                start_date = st.date_input(
                    "תאריך התחלה", value=None, format="DD/MM/YYYY", key=f"tool6_period_start_{worker_id}"
                )
            with row2_col2:
                end_date = st.date_input(
                    "תאריך סיום", value=None, format="DD/MM/YYYY", key=f"tool6_period_end_{worker_id}"
                )
            note = st.text_area("הערה (אופציונלי)")
            submitted = st.form_submit_button("הוסף תקופה", type="primary", width="stretch")

        if submitted:
            validation_error = _validate_period_fields(
                period_type=period_type, start_date=start_date, end_date=end_date
            )
            if validation_error:
                st.error(validation_error)
                return
            values = [
                _new_period_id(),
                worker_id,
                period_type,
                framework.strip(),
                subunit.strip(),
                location.strip(),
                start_date.strftime("%d/%m/%Y"),
                end_date.strftime("%d/%m/%Y"),
                note.strip(),
                _now_text(),
            ]
            try:
                _append_period(st, values)
            except Exception as exc:
                st.error(f"שמירת התקופה נכשלה: {exc}")
                return
            st.success("התקופה נוספה בהצלחה.")
            st.rerun()
        return

    if not worker_periods:
        st.info("אין תקופה קיימת שניתן לערוך.")
        return

    period_labels: list[str] = []
    periods_by_label: dict[str, dict[str, object]] = {}
    for item in worker_periods:
        label = (
            f"{item['period_type']} - {_format_date(item.get('start_date'))} עד "
            f"{_format_date(item.get('end_date'))}"
        )
        if label in periods_by_label:
            label = f"{label} - {item['period_id']}"
        period_labels.append(label)
        periods_by_label[label] = item

    selected_period_label = st.selectbox(
        "תקופה", period_labels, key=f"tool6_period_edit_select_{worker_id}"
    )
    selected_period = periods_by_label[selected_period_label]
    period_id = str(selected_period["period_id"])
    period_row_number = int(selected_period["row_number"])
    period_type_options = _option_list(PERIOD_TYPE_OPTIONS, str(selected_period["period_type"]))
    current_period_type = str(selected_period["period_type"])

    with st.form(f"tool6_edit_period_form_{period_id}", clear_on_submit=False):
        period_type = st.selectbox(
            "סוג תקופה",
            period_type_options,
            index=(
                period_type_options.index(current_period_type)
                if current_period_type in period_type_options
                else 0
            ),
        )
        row1_col1, row1_col2 = st.columns(2)
        with row1_col1:
            framework = st.text_input(
                "מסגרת / מחלקה (אופציונלי)", value=str(selected_period["framework"])
            )
        with row1_col2:
            subunit = st.text_input(
                "תת-יחידה / רוטציה (אופציונלי)", value=str(selected_period["subunit"])
            )
        location = st.text_input("מקום (אופציונלי)", value=str(selected_period["location"]))
        row2_col1, row2_col2 = st.columns(2)
        with row2_col1:
            start_date = st.date_input(
                "תאריך התחלה",
                value=selected_period.get("start_date"),
                format="DD/MM/YYYY",
                key=f"tool6_period_edit_start_{period_id}",
            )
        with row2_col2:
            end_date = st.date_input(
                "תאריך סיום",
                value=selected_period.get("end_date"),
                format="DD/MM/YYYY",
                key=f"tool6_period_edit_end_{period_id}",
            )
        note = st.text_area("הערה (אופציונלי)", value=str(selected_period["note"]))
        submitted = st.form_submit_button("שמור שינויים", type="primary", width="stretch")

    if not submitted:
        st.caption("אין מחיקה של תקופות דרך הממשק. ניתן לעדכן תקופה קיימת לפי הצורך.")
        return

    validation_error = _validate_period_fields(
        period_type=period_type, start_date=start_date, end_date=end_date
    )
    if validation_error:
        st.error(validation_error)
        return

    values = [
        period_id,
        worker_id,
        period_type,
        framework.strip(),
        subunit.strip(),
        location.strip(),
        start_date.strftime("%d/%m/%Y"),
        end_date.strftime("%d/%m/%Y"),
        note.strip(),
        _now_text(),
    ]
    try:
        _update_period_row(st, period_row_number, values)
    except Exception as exc:
        st.error(f"עדכון התקופה נכשל: {exc}")
        return
    st.success("התקופה עודכנה בהצלחה.")
    st.rerun()


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
    if action == "עריכת עובד/ת":
        _render_edit_worker(st)
        return
    if action == "צפייה ברשימת עובדים":
        _render_worker_list(st, app_module.pd)
        return
    _render_periods(st, app_module.pd)
