"""Self-registration UI for people not yet present in Workers.

This wrapper keeps the existing employee login behavior and adds a pending
registration path. Personal facts are collected here; organizational fields
remain manager-owned and are added only during approval in Tool 6.
"""
from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo
from datetime import datetime

import entry_flow
from worker_profile_rules import birth_date_input_values
from worker_registrations import (
    CHILDREN_OPTIONS,
    MARITAL_STATUS_OPTIONS,
    STATUS_APPROVED,
    STATUS_PENDING,
    latest_registration_by_id,
    submit_registration,
)


REGISTRATION_FORM_KEY = "medstaff_new_worker_registration_v1"
REGISTRATION_ID_KEY = "medstaff_new_worker_id_number_v1"
SELECT_PLACEHOLDER = "בחר/י..."


def _render_registration_form(st) -> None:
    entry_flow._hide_sidebar(st)
    entry_flow._render_brand(st)

    _, center, _ = st.columns([1, 2, 1])
    with center:
        if st.button("חזרה לזיהוי", key="new_worker_registration_back_v1"):
            st.session_state.pop(REGISTRATION_FORM_KEY, None)
            st.rerun()

        st.markdown("### הצטרפות עובד/ת חדש/ה")
        st.caption(
            "יש למלא פרטים אישיים בלבד. פרטים מקצועיים, תאריכי פעילות, כשירויות ורוטציות "
            "יושלמו על ידי מנהל/ת המערכת לאחר בדיקה."
        )

        id_number = str(st.session_state.get(REGISTRATION_ID_KEY, "") or "")
        birth_default, earliest_birth_date, latest_birth_date = birth_date_input_values()

        with st.form("new_worker_registration_form_v1", clear_on_submit=False):
            st.text_input("ת.ז", value=id_number, disabled=True)

            row1_col1, row1_col2 = st.columns(2)
            with row1_col1:
                first_name = st.text_input("שם פרטי")
            with row1_col2:
                last_name = st.text_input("שם משפחה")

            birth_date = st.date_input(
                "תאריך לידה",
                value=birth_default,
                min_value=earliest_birth_date,
                max_value=latest_birth_date,
                format="DD/MM/YYYY",
            )

            row2_col1, row2_col2 = st.columns(2)
            with row2_col1:
                address = st.text_input("כתובת")
            with row2_col2:
                locality = st.text_input("יישוב מגורים")

            row3_col1, row3_col2 = st.columns(2)
            with row3_col1:
                phone = st.text_input("טלפון")
            with row3_col2:
                email = st.text_input("אימייל")

            row4_col1, row4_col2 = st.columns(2)
            with row4_col1:
                marital_status = st.selectbox(
                    "מצב משפחתי",
                    [SELECT_PLACEHOLDER, *MARITAL_STATUS_OPTIONS],
                )
            with row4_col2:
                children = st.selectbox(
                    "מספר ילדים",
                    [SELECT_PLACEHOLDER, *CHILDREN_OPTIONS],
                )

            submitted = st.form_submit_button(
                "שליחת בקשה לאישור",
                type="primary",
                width="stretch",
            )

        if not submitted:
            return

        if marital_status == SELECT_PLACEHOLDER:
            st.error("יש לבחור מצב משפחתי.")
            return
        if children == SELECT_PLACEHOLDER:
            st.error("יש לבחור מספר ילדים.")
            return

        try:
            submit_registration(
                st,
                id_number=id_number,
                first_name=first_name,
                last_name=last_name,
                birth_date=birth_date,
                address=address,
                locality=locality,
                phone=phone,
                email=email,
                marital_status=marital_status,
                children=children,
            )
        except Exception as exc:
            st.error(f"לא ניתן לשלוח את בקשת ההצטרפות: {exc}")
            return

        st.session_state.pop(REGISTRATION_FORM_KEY, None)
        st.session_state[entry_flow.EMPLOYEE_LOOKUP_RESULT_KEY] = "registration_pending"
        st.success("הבקשה נשלחה למנהל/ת המערכת לאישור.")
        st.rerun()


def _render_employee_login_with_registration(st) -> None:
    if st.session_state.get(REGISTRATION_FORM_KEY):
        _render_registration_form(st)
        return

    entry_flow._hide_sidebar(st)
    entry_flow._render_brand(st)

    _, center, _ = st.columns([1, 2, 1])
    with center:
        if st.button("חזרה", key="employee_entry_back_v1"):
            entry_flow._clear_entry_state(st)
            st.session_state.pop(REGISTRATION_FORM_KEY, None)
            st.session_state.pop(REGISTRATION_ID_KEY, None)
            st.rerun()

        st.markdown("### זיהוי עובד/ת")
        st.caption("יש להזין תעודת זהות כדי להמשיך להזנת ההעדפות.")

        with st.form("employee_id_lookup_form_v1"):
            entered_id = st.text_input(
                "תעודת זהות",
                placeholder="9 ספרות",
                max_chars=12,
            )
            submitted = st.form_submit_button("המשך", type="primary", width="stretch")

        if submitted:
            normalized = entry_flow.normalize_id_number(entered_id)
            st.session_state[REGISTRATION_ID_KEY] = normalized
            if len(normalized) != 9:
                st.session_state[entry_flow.EMPLOYEE_LOOKUP_RESULT_KEY] = "invalid"
            else:
                try:
                    worker = entry_flow.find_worker_by_id_number(st, normalized)
                except Exception as exc:
                    st.error(f"לא ניתן לבדוק את פרטי העובד/ת: {exc}")
                    return

                if worker is None:
                    try:
                        registration = latest_registration_by_id(st, normalized)
                    except Exception as exc:
                        st.error(f"לא ניתן לבדוק בקשות הצטרפות קיימות: {exc}")
                        return
                    if registration and registration.get("status") in {STATUS_PENDING, STATUS_APPROVED}:
                        st.session_state[entry_flow.EMPLOYEE_LOOKUP_RESULT_KEY] = "registration_pending"
                    else:
                        st.session_state[entry_flow.EMPLOYEE_LOOKUP_RESULT_KEY] = "not_found"
                elif worker.get("status") != entry_flow.STATUS_ACTIVE:
                    st.session_state[entry_flow.EMPLOYEE_LOOKUP_RESULT_KEY] = "inactive"
                else:
                    try:
                        system_user = entry_flow.ensure_employee_user(st, worker)
                    except Exception as exc:
                        st.error(f"לא ניתן לאמת את הרשאת הכניסה: {exc}")
                        return

                    if system_user.get("status") != entry_flow.STATUS_ACTIVE:
                        st.session_state[entry_flow.EMPLOYEE_LOOKUP_RESULT_KEY] = "access_inactive"
                    else:
                        try:
                            entry_flow.log_access(
                                st,
                                user=system_user,
                                entry_type="עובד/ת",
                                result="הצלחה",
                            )
                        except Exception as exc:
                            st.error(f"לא ניתן לתעד את הכניסה למערכת: {exc}")
                            return

                        st.session_state[entry_flow.IDENTIFIED_WORKER_KEY] = worker
                        st.session_state[entry_flow.IDENTIFIED_EMPLOYEE_USER_KEY] = system_user
                        st.session_state["preferences_employee"] = worker["full_name"]
                        st.session_state[entry_flow.EMPLOYEE_LOOKUP_RESULT_KEY] = "found"
                        st.rerun()

        result = st.session_state.get(entry_flow.EMPLOYEE_LOOKUP_RESULT_KEY)
        if result == "invalid":
            st.error("יש להזין תעודת זהות בת 9 ספרות.")
        elif result == "not_found":
            st.warning("לא נמצא עובד/ת עם תעודת הזהות שהוזנה. כדאי לבדוק את המספר ולנסות שוב.")
            if st.button("אני עובד/ת חדש/ה", width="stretch", key="new_employee_start_v1"):
                st.session_state[REGISTRATION_FORM_KEY] = True
                st.rerun()
        elif result == "registration_pending":
            st.info("בקשת ההצטרפות שלך ממתינה לאישור מנהל/ת המערכת. לאחר האישור ניתן יהיה להיכנס כעובד/ת.")
        elif result == "inactive":
            st.warning("העובד/ת נמצא/ה במערכת אך אינו/ה מסומן/ת כפעיל/ה. יש לפנות למנהל/ת המערכת.")
        elif result == "access_inactive":
            st.warning("חשבון המשתמש אינו פעיל. יש לפנות למנהל/ת המערכת.")


def install(app_module) -> None:
    """Install self-registration before entry_flow.install wraps app.main."""
    if getattr(entry_flow, "_employee_registration_override_installed", False):
        return
    entry_flow._render_employee_login = _render_employee_login_with_registration
    entry_flow._employee_registration_override_installed = True
