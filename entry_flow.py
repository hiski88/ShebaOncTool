"""Role-based entry flow for the oncology MedStaff prototype.

The entry layer is deliberately separate from the scheduling tools:
- employees identify themselves using their ID number and are mapped to Worker ID;
- managers authenticate with the existing manager secret and then receive the full tool navigation;
- the sidebar stays hidden until manager access is granted.
"""
from __future__ import annotations

import re

from google_sheets_submissions import _service


MANAGER_PASSWORD_SECRET = "MANAGER_TOOLS_PASSWORD"
WORKERS_SHEET = "Workers"
ENTRY_MODE_KEY = "medstaff_entry_mode_v1"
IDENTIFIED_WORKER_KEY = "medstaff_identified_worker_v1"
EMPLOYEE_LOOKUP_RESULT_KEY = "medstaff_employee_lookup_result_v1"


def _hide_sidebar(st) -> None:
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] { display: none !important; }
        [data-testid="stSidebarCollapsedControl"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _normalize_id_number(value: object) -> str:
    """Normalize an Israeli-style ID for lookup without making it the internal key."""
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    if len(digits) <= 9:
        return digits.zfill(9)
    return digits


def _read_workers(st) -> list[list[str]]:
    service, spreadsheet_id, _ = _service(st)
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{WORKERS_SHEET}'!A2:S",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    return response.get("values", [])


def _lookup_worker(st, id_number: str) -> dict[str, str] | None:
    normalized = _normalize_id_number(id_number)
    if len(normalized) != 9:
        return None

    matches: list[dict[str, str]] = []
    for raw in _read_workers(st):
        row = [str(item) for item in raw] + [""] * (19 - len(raw))
        stored_id = _normalize_id_number(row[3])
        if stored_id != normalized:
            continue
        first_name = row[1].strip()
        last_name = row[2].strip()
        matches.append(
            {
                "worker_id": row[0].strip(),
                "first_name": first_name,
                "last_name": last_name,
                "full_name": " ".join(part for part in (first_name, last_name) if part).strip(),
                "id_number": normalized,
                "status": row[12].strip(),
            }
        )

    if len(matches) > 1:
        raise RuntimeError("נמצאו מספר רשומות עם אותה ת.ז. יש לפנות למנהל/ת המערכת.")
    return matches[0] if matches else None


def _clear_entry_state(st) -> None:
    for key in (
        ENTRY_MODE_KEY,
        IDENTIFIED_WORKER_KEY,
        EMPLOYEE_LOOKUP_RESULT_KEY,
        "preferences_employee",
        "manager_tools_authenticated",
        "staff_tools_authenticated",
        "tool2_planner_authenticated",
    ):
        st.session_state.pop(key, None)


def _render_brand(st) -> None:
    st.markdown(
        """
        <div style="text-align:center; padding:2.4rem 0 1.2rem 0;">
          <div style="font-size:2.7rem; font-weight:750; line-height:1.05;">MedStaff</div>
          <div style="font-size:1.2rem; font-weight:650; margin-top:.55rem;">המערך האונקולוגי - המרכז הרפואי שיבא</div>
          <div style="font-size:1.02rem; color:#5f6b7a; margin:.8rem auto 0 auto; max-width:720px;">
            מערכת לתכנון, תיאום וניהול עבודת המתמחים והמתמחות במערך האונקולוגי
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_welcome(st) -> None:
    _hide_sidebar(st)
    _render_brand(st)

    _, center, _ = st.columns([1, 3, 1])
    with center:
        st.markdown("### כניסה למערכת")
        employee_col, manager_col = st.columns(2, gap="large")
        with employee_col:
            with st.container(border=True):
                st.markdown("#### עובד/ת")
                st.caption("הזנת העדפות וגישה לכלים האישיים.")
                if st.button("כניסת עובד/ת", type="primary", width="stretch", key="entry_employee_v1"):
                    st.session_state[ENTRY_MODE_KEY] = "employee"
                    st.rerun()
        with manager_col:
            with st.container(border=True):
                st.markdown("#### מנהל/ת מערכת")
                st.caption("תכנון, סידור וניהול עובדים.")
                if st.button("כניסת מנהל/ת", width="stretch", key="entry_manager_v1"):
                    st.session_state[ENTRY_MODE_KEY] = "manager"
                    st.rerun()


def _render_employee_login(st) -> None:
    _hide_sidebar(st)
    _render_brand(st)

    _, center, _ = st.columns([1, 2, 1])
    with center:
        if st.button("חזרה", key="employee_entry_back_v1"):
            _clear_entry_state(st)
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
            normalized = _normalize_id_number(entered_id)
            if len(normalized) != 9:
                st.session_state[EMPLOYEE_LOOKUP_RESULT_KEY] = "invalid"
            else:
                try:
                    worker = _lookup_worker(st, normalized)
                except Exception as exc:
                    st.error(f"לא ניתן לבדוק את פרטי העובד/ת: {exc}")
                    return

                if worker is None:
                    st.session_state[EMPLOYEE_LOOKUP_RESULT_KEY] = "not_found"
                elif worker.get("status") != "פעיל":
                    st.session_state[EMPLOYEE_LOOKUP_RESULT_KEY] = "inactive"
                else:
                    st.session_state[IDENTIFIED_WORKER_KEY] = worker
                    st.session_state["preferences_employee"] = worker["full_name"]
                    st.session_state[EMPLOYEE_LOOKUP_RESULT_KEY] = "found"
                    st.rerun()

        result = st.session_state.get(EMPLOYEE_LOOKUP_RESULT_KEY)
        if result == "invalid":
            st.error("יש להזין תעודת זהות בת 9 ספרות.")
        elif result == "not_found":
            st.warning("לא נמצא עובד/ת עם תעודת הזהות שהוזנה. כדאי לבדוק את המספר ולנסות שוב.")
            if st.button("אני עובד/ת חדש/ה", width="stretch", key="new_employee_start_v1"):
                st.info("טופס הצטרפות לעובד/ת חדש/ה יתווסף בשלב הבא.")
        elif result == "inactive":
            st.warning("העובד/ת נמצא/ה במערכת אך אינו/ה מסומן/ת כפעיל/ה. יש לפנות למנהל/ת המערכת.")


def _render_employee_tool(st, app_module) -> None:
    _hide_sidebar(st)
    worker = st.session_state.get(IDENTIFIED_WORKER_KEY)
    if not isinstance(worker, dict) or not worker.get("worker_id"):
        st.session_state.pop(IDENTIFIED_WORKER_KEY, None)
        st.session_state[ENTRY_MODE_KEY] = "employee"
        st.rerun()

    top_left, top_right = st.columns([5, 1])
    with top_left:
        st.caption(f"מחובר/ת כ-{worker.get('full_name', '')}")
    with top_right:
        if st.button("החלפת משתמש", width="stretch", key="employee_logout_v1"):
            _clear_entry_state(st)
            st.rerun()

    st.session_state["preferences_employee"] = str(worker.get("full_name", ""))
    app_module.tool_preferences()


def _render_manager_login(st) -> None:
    _hide_sidebar(st)
    _render_brand(st)

    _, center, _ = st.columns([1, 2, 1])
    with center:
        if st.button("חזרה", key="manager_entry_back_v1"):
            _clear_entry_state(st)
            st.rerun()

        st.markdown("### כניסת מנהל/ת מערכת")
        try:
            expected = str(st.secrets.get(MANAGER_PASSWORD_SECRET, "") or "")
        except Exception as exc:
            st.error(f"לא ניתן לקרוא את הגדרות הגישה: {exc}")
            return

        if not expected:
            st.error("סיסמת מנהל/ת המערכת אינה מוגדרת.")
            return

        with st.form("manager_entry_form_v1"):
            password = st.text_input("סיסמה", type="password")
            submitted = st.form_submit_button("כניסה", type="primary", width="stretch")

        if submitted:
            if password != expected:
                st.error("סיסמה שגויה.")
                return
            st.session_state["manager_tools_authenticated"] = True
            st.session_state["staff_tools_authenticated"] = True
            st.session_state["tool2_planner_authenticated"] = True
            st.rerun()


def install(app_module) -> None:
    """Wrap the already-installed tool navigation with the role-based entry gate."""
    if getattr(app_module, "_entry_flow_installed", False):
        return

    original_main = app_module.main

    def main_with_entry() -> None:
        st = app_module.st
        mode = st.session_state.get(ENTRY_MODE_KEY)

        if mode == "employee":
            if isinstance(st.session_state.get(IDENTIFIED_WORKER_KEY), dict):
                _render_employee_tool(st, app_module)
            else:
                _render_employee_login(st)
            return

        if mode == "manager":
            if not st.session_state.get("manager_tools_authenticated", False):
                _render_manager_login(st)
                return

            if st.sidebar.button("יציאה / החלפת מצב", width="stretch", key="manager_logout_v1"):
                _clear_entry_state(st)
                st.rerun()
            st.sidebar.divider()
            original_main()
            return

        _render_welcome(st)

    app_module.main = main_with_entry
    app_module._entry_flow_installed = True
