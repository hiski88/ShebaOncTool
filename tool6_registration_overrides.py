"""Manager review of pending worker self-registrations inside Tool 6."""
from __future__ import annotations

from system_users import MANAGER_USER_SESSION_KEY
from worker_registrations import (
    approve_registration,
    pending_registrations,
    reject_registration,
)


def _render_pending_registrations(st, tool6) -> None:
    st.subheader("בקשות הצטרפות")
    st.caption(
        "העובד/ת ממלא/ת פרטים אישיים בלבד. מנהל/ת המערכת משלים/ה את הפרטים "
        "המקצועיים ורק לאחר אישור נוצרת רשומה ב-Workers."
    )

    try:
        pending = pending_registrations(st)
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את בקשות ההצטרפות: {exc}")
        return

    if not pending:
        st.success("אין כרגע בקשות הצטרפות הממתינות לאישור.")
        return

    pending.sort(key=lambda item: (item.get("submitted_at", ""), item.get("registration_id", "")))
    labels: list[str] = []
    by_label: dict[str, dict[str, str]] = {}
    for item in pending:
        full_name = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip()
        label = f"{full_name} - {item.get('submitted_at', '')}"
        if label in by_label:
            label = f"{label} - {item.get('registration_id', '')}"
        labels.append(label)
        by_label[label] = item

    selected_label = st.selectbox("בקשה", labels, key="tool6_registration_select_v1")
    registration = by_label[selected_label]
    registration_id = registration["registration_id"]
    birth_date = tool6._parse_sheet_date(registration.get("birth_date"))

    with st.container(border=True):
        st.markdown("#### פרטים שנמסרו על ידי העובד/ת")
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**שם:** {registration.get('first_name', '')} {registration.get('last_name', '')}")
            st.write(f"**ת.ז:** {registration.get('id_number', '')}")
            st.write(f"**תאריך לידה:** {registration.get('birth_date', '')}")
            st.write(f"**טלפון:** {registration.get('phone', '')}")
            st.write(f"**אימייל:** {registration.get('email', '')}")
        with c2:
            st.write(f"**כתובת:** {registration.get('address', '')}")
            st.write(f"**יישוב:** {registration.get('locality', '')}")
            st.write(f"**מצב משפחתי:** {registration.get('marital_status', '')}")
            st.write(f"**מספר ילדים:** {registration.get('children', '')}")
            st.write(f"**נשלח:** {registration.get('submitted_at', '')}")

    with st.form(f"tool6_registration_review_{registration_id}", clear_on_submit=False):
        st.markdown("#### השלמת פרטים מקצועיים")
        row1_col1, row1_col2 = st.columns(2)
        with row1_col1:
            track = tool6._required_selectbox(st, "מסלול / התמחות", tool6.TRACK_OPTIONS)
        with row1_col2:
            status = st.selectbox("סטטוס", tool6.STATUS_OPTIONS, index=0)

        row2_col1, row2_col2 = st.columns(2)
        with row2_col1:
            eligibility = tool6._required_selectbox(st, "כשירות תורנויות", tool6.ELIGIBILITY_OPTIONS)
        with row2_col2:
            basic_science_exemption = tool6._required_selectbox(
                st, "פטור מדעי יסוד", tool6.YES_NO_OPTIONS
            )

        row3_col1, row3_col2 = st.columns(2)
        with row3_col1:
            department_start = st.date_input(
                "תאריך תחילת פעילות במחלקה",
                value=None,
                format="DD/MM/YYYY",
            )
        with row3_col2:
            specialization_start = st.date_input(
                "תאריך תחילת התמחות",
                value=None,
                format="DD/MM/YYYY",
            )

        general_note = st.text_area("הערה כללית לעובד/ת (אופציונלי)")
        manager_note = st.text_area("הערת מנהל לבקשה (אופציונלי)")

        approve_col, reject_col = st.columns(2)
        with approve_col:
            approve_clicked = st.form_submit_button(
                "אשר/י והוסף/י ל-Workers",
                type="primary",
                width="stretch",
            )
        with reject_col:
            reject_clicked = st.form_submit_button(
                "דחה/י בקשה",
                width="stretch",
            )

    manager_user = st.session_state.get(MANAGER_USER_SESSION_KEY, {})
    actor_user_id = str(manager_user.get("user_id", "SYSTEM") if isinstance(manager_user, dict) else "SYSTEM")

    if reject_clicked:
        try:
            reject_registration(
                st,
                registration_id=registration_id,
                actor_user_id=actor_user_id,
                manager_note=manager_note,
            )
        except Exception as exc:
            st.error(f"דחיית הבקשה נכשלה: {exc}")
            return
        st.success("בקשת ההצטרפות נדחתה.")
        st.rerun()

    if not approve_clicked:
        return

    if birth_date is None:
        st.error("תאריך הלידה בבקשה אינו תקין. יש לתקן את הנתון לפני אישור.")
        return

    validation_error = tool6._validate_worker_fields(
        first_name=registration.get("first_name", ""),
        last_name=registration.get("last_name", ""),
        id_number=registration.get("id_number", ""),
        birth_date=birth_date,
        address=registration.get("address", ""),
        locality=registration.get("locality", ""),
        phone=registration.get("phone", ""),
        email=registration.get("email", ""),
        marital_status=registration.get("marital_status", ""),
        children=registration.get("children", ""),
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
        worker_id = approve_registration(
            st,
            registration_id=registration_id,
            actor_user_id=actor_user_id,
            track=track,
            status=status,
            eligibility=eligibility,
            basic_science_exemption=basic_science_exemption,
            department_start=department_start,
            specialization_start=specialization_start,
            general_note=general_note,
            manager_note=manager_note,
        )
    except Exception as exc:
        st.error(f"אישור הבקשה נכשל: {exc}")
        return

    st.success(f"הבקשה אושרה והעובד/ת נוסף/ה למערכת. Worker ID: {worker_id}")
    st.rerun()


def install(app_module) -> None:
    """Extend Tool 6 before other Tool 6 wrappers capture its renderer."""
    import tool6_workers as tool6

    if getattr(tool6, "_tool6_registration_override_installed", False):
        return

    def render_with_registrations(module) -> None:
        st = module.st
        module.render_header(
            "6. ניהול עובדים",
            "ניהול מצבת עובדים, פרטים תעסוקתיים ותקופות התמחות.",
        )

        try:
            pending_count = len(pending_registrations(st))
        except Exception:
            pending_count = 0
        if pending_count:
            st.info(f"ממתינות {pending_count} בקשות הצטרפות לאישור.")

        action = st.radio(
            "בחירת פעולה",
            [
                "אישור עובדים",
                "הוספת עובד/ת",
                "עריכת עובד/ת",
                "צפייה ברשימת עובדים",
                "ניהול התמחות ותקופות",
            ],
            key="tool6_action",
        )

        st.divider()
        if action == "אישור עובדים":
            _render_pending_registrations(st, tool6)
            return
        if action == "הוספת עובד/ת":
            tool6._render_add_worker(st)
            return
        if action == "עריכת עובד/ת":
            tool6._render_edit_worker(st)
            return
        if action == "צפייה ברשימת עובדים":
            tool6._render_worker_list(st, module.pd)
            return
        tool6._render_periods(st, module.pd)

    tool6.render = render_with_registrations
    tool6._tool6_registration_override_installed = True
