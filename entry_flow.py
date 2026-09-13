"""Role-based entry flow for the oncology MedStaff prototype.

Identity and authorization are intentionally separate from scheduling data:
- employees identify with ID number, map to Worker ID and receive/resolve a SystemUser;
- managers must exist in SystemUsers and also pass the shared manager secret;
- the first permission administrator can be bootstrapped with the existing secret;
- successful employee/manager entries and manager authentication failures are logged.
"""
from __future__ import annotations

from system_users import (
    MANAGER_ROLES,
    MANAGER_USER_SESSION_KEY,
    ROLE_ACCESS_ADMIN,
    STATUS_ACTIVE,
    ensure_employee_user,
    find_worker_by_id_number,
    log_access,
    lookup_user_by_id,
    manager_users_exist,
    normalize_id_number,
)


MANAGER_PASSWORD_SECRET = "MANAGER_TOOLS_PASSWORD"
ENTRY_MODE_KEY = "medstaff_entry_mode_v1"
IDENTIFIED_WORKER_KEY = "medstaff_identified_worker_v1"
IDENTIFIED_EMPLOYEE_USER_KEY = "medstaff_employee_system_user_v1"
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


def _clear_entry_state(st) -> None:
    for key in (
        ENTRY_MODE_KEY,
        IDENTIFIED_WORKER_KEY,
        IDENTIFIED_EMPLOYEE_USER_KEY,
        EMPLOYEE_LOOKUP_RESULT_KEY,
        MANAGER_USER_SESSION_KEY,
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
                st.caption("תכנון, סידור, ניהול עובדים והרשאות.")
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
            normalized = normalize_id_number(entered_id)
            if len(normalized) != 9:
                st.session_state[EMPLOYEE_LOOKUP_RESULT_KEY] = "invalid"
            else:
                try:
                    worker = find_worker_by_id_number(st, normalized)
                except Exception as exc:
                    st.error(f"לא ניתן לבדוק את פרטי העובד/ת: {exc}")
                    return

                if worker is None:
                    st.session_state[EMPLOYEE_LOOKUP_RESULT_KEY] = "not_found"
                elif worker.get("status") != STATUS_ACTIVE:
                    st.session_state[EMPLOYEE_LOOKUP_RESULT_KEY] = "inactive"
                else:
                    try:
                        system_user = ensure_employee_user(st, worker)
                    except Exception as exc:
                        st.error(f"לא ניתן לאמת את הרשאת הכניסה: {exc}")
                        return

                    if system_user.get("status") != STATUS_ACTIVE:
                        st.session_state[EMPLOYEE_LOOKUP_RESULT_KEY] = "access_inactive"
                    else:
                        try:
                            log_access(
                                st,
                                user=system_user,
                                entry_type="עובד/ת",
                                result="הצלחה",
                            )
                        except Exception as exc:
                            st.error(f"לא ניתן לתעד את הכניסה למערכת: {exc}")
                            return

                        st.session_state[IDENTIFIED_WORKER_KEY] = worker
                        st.session_state[IDENTIFIED_EMPLOYEE_USER_KEY] = system_user
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
        elif result == "access_inactive":
            st.warning("חשבון המשתמש אינו פעיל. יש לפנות למנהל/ת המערכת.")


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


def _manager_secret(st) -> str:
    try:
        return str(st.secrets.get(MANAGER_PASSWORD_SECRET, "") or "")
    except Exception as exc:
        raise RuntimeError(f"לא ניתן לקרוא את הגדרות הגישה: {exc}") from exc


def _set_manager_session(st, user: dict[str, str]) -> None:
    st.session_state[MANAGER_USER_SESSION_KEY] = user
    st.session_state["manager_tools_authenticated"] = True
    st.session_state["staff_tools_authenticated"] = True
    st.session_state["tool2_planner_authenticated"] = True


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
            expected = _manager_secret(st)
        except Exception as exc:
            st.error(str(exc))
            return

        if not expected:
            st.error("סיסמת מנהל/ת המערכת אינה מוגדרת.")
            return

        try:
            has_defined_managers = manager_users_exist(st)
        except Exception as exc:
            st.error(f"לא ניתן לקרוא את משתמשי המערכת: {exc}")
            return

        if not has_defined_managers:
            st.info(
                "טרם הוגדר מנהל/ת מערכת ב-SystemUsers. הכניסה הראשונית מתבצעת באמצעות "
                "סיסמת המנהל הקיימת, ולאחר מכן יש להגדיר מנהל/ת הרשאות בכלי 7."
            )
            with st.form("manager_bootstrap_form_v1"):
                password = st.text_input("סיסמת מנהל/ת", type="password")
                submitted = st.form_submit_button("כניסה ראשונית", type="primary", width="stretch")

            if not submitted:
                return

            bootstrap_user = {
                "user_id": "BOOTSTRAP",
                "display_name": "הקמה ראשונית",
                "role": ROLE_ACCESS_ADMIN,
                "worker_id": "",
                "status": STATUS_ACTIVE,
                "bootstrap": True,
            }
            if password != expected:
                try:
                    log_access(st, user=bootstrap_user, entry_type="מנהל/ת", result="כשל אימות")
                except Exception:
                    pass
                st.error("סיסמה שגויה.")
                return

            try:
                log_access(st, user=bootstrap_user, entry_type="מנהל/ת", result="הצלחה - הקמה ראשונית")
            except Exception as exc:
                st.error(f"לא ניתן לתעד את הכניסה למערכת: {exc}")
                return
            _set_manager_session(st, bootstrap_user)
            st.rerun()

        with st.form("manager_entry_form_v2"):
            id_number = st.text_input("תעודת זהות", placeholder="9 ספרות", max_chars=12)
            password = st.text_input("סיסמת מנהל/ת", type="password")
            submitted = st.form_submit_button("כניסה", type="primary", width="stretch")

        if not submitted:
            return

        normalized = normalize_id_number(id_number)
        user = None
        if len(normalized) == 9:
            try:
                user = lookup_user_by_id(st, normalized)
            except Exception as exc:
                st.error(f"לא ניתן לבדוק את הרשאת המשתמש: {exc}")
                return

        if user is None:
            try:
                log_access(st, user=None, entry_type="מנהל/ת", result="משתמש לא נמצא")
            except Exception:
                pass
            st.error("פרטי הכניסה אינם תקינים.")
            return

        if user.get("status") != STATUS_ACTIVE or user.get("role") not in MANAGER_ROLES:
            try:
                log_access(st, user=user, entry_type="מנהל/ת", result="אין הרשאת מנהל פעילה")
            except Exception:
                pass
            st.error("למשתמש/ת אין הרשאת מנהל פעילה.")
            return

        if password != expected:
            try:
                log_access(st, user=user, entry_type="מנהל/ת", result="כשל אימות")
            except Exception:
                pass
            st.error("סיסמה שגויה.")
            return

        try:
            log_access(st, user=user, entry_type="מנהל/ת", result="הצלחה")
        except Exception as exc:
            st.error(f"לא ניתן לתעד את הכניסה למערכת: {exc}")
            return

        _set_manager_session(st, user)
        st.rerun()


def install(app_module) -> None:
    """Wrap the installed tool navigation with identity and authorization gates."""
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
            manager_user = st.session_state.get(MANAGER_USER_SESSION_KEY)
            if (
                not st.session_state.get("manager_tools_authenticated", False)
                or not isinstance(manager_user, dict)
                or not manager_user.get("user_id")
            ):
                st.session_state.pop("manager_tools_authenticated", None)
                _render_manager_login(st)
                return

            st.sidebar.caption(
                f"מחובר/ת: {manager_user.get('display_name', '')} | {manager_user.get('role', '')}"
            )
            if st.sidebar.button("יציאה / החלפת מצב", width="stretch", key="manager_logout_v1"):
                _clear_entry_state(st)
                st.rerun()
            st.sidebar.divider()
            original_main()
            return

        _render_welcome(st)

    app_module.main = main_with_entry
    app_module._entry_flow_installed = True
