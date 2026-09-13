"""Tool 7 - system users, permissions and access logs."""
from __future__ import annotations

from system_users import (
    MANAGER_USER_SESSION_KEY,
    ROLE_ACCESS_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_MANAGER,
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    SYSTEM_ROLES,
    active_access_admin_count,
    create_system_user,
    find_worker_by_id_number,
    list_users,
    read_access_log,
    read_audit_log,
    update_system_user,
)


ADD_ROLE_OPTIONS = [ROLE_MANAGER, ROLE_ACCESS_ADMIN, ROLE_EMPLOYEE]


def _current_manager(st) -> dict[str, str]:
    value = st.session_state.get(MANAGER_USER_SESSION_KEY)
    return value if isinstance(value, dict) else {}


def _can_manage_permissions(st, current: dict[str, str]) -> bool:
    if bool(current.get("bootstrap")):
        return True
    if current.get("role") == ROLE_ACCESS_ADMIN:
        return True
    # Recovery path: if no active permission administrator remains, an active
    # system manager may restore one instead of permanently locking the system.
    if current.get("role") == ROLE_MANAGER:
        try:
            return active_access_admin_count(st) == 0
        except Exception:
            return False
    return False


def _render_add_user(st, current: dict[str, str]) -> None:
    st.subheader("הוספת משתמש/ת מערכת")
    st.caption(
        "משתמש מערכת אינו חייב להיות עובד המנוהל בסידור. אם תעודת הזהות שייכת לעובד/ת קיים/ת, "
        "המערכת תקשר אוטומטית את ה-Worker ID."
    )

    try:
        no_access_admin = active_access_admin_count(st) == 0
    except Exception as exc:
        st.error(f"לא ניתן לבדוק את הרשאות המערכת: {exc}")
        return

    if no_access_admin:
        st.warning(
            "כרגע אין מנהל/ת הרשאות פעיל/ה. המשתמש הראשון שיוגדר במסך זה חייב להיות מנהל/ת הרשאות."
        )

    with st.form("tool7_add_user_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            id_number = st.text_input("ת.ז", key="tool7_add_id")
        with col2:
            display_name = st.text_input(
                "שם לתצוגה",
                help="אם מדובר בעובד/ת קיים/ת אפשר להשאיר ריק והשם יילקח מטבלת העובדים.",
                key="tool7_add_name",
            )

        if no_access_admin:
            role = ROLE_ACCESS_ADMIN
            st.text_input("תפקיד מערכת", value=ROLE_ACCESS_ADMIN, disabled=True, key="tool7_add_role_locked")
        else:
            role = st.selectbox("תפקיד מערכת", ADD_ROLE_OPTIONS, key="tool7_add_role")

        note = st.text_area("הערה (אופציונלי)", key="tool7_add_note")
        submitted = st.form_submit_button("הוסף משתמש/ת", type="primary", width="stretch")

    if not submitted:
        return

    try:
        worker = find_worker_by_id_number(st, id_number)
    except Exception as exc:
        st.error(f"לא ניתן לבדוק קישור לעובד/ת: {exc}")
        return

    worker_id = str((worker or {}).get("worker_id", "") or "").strip()
    resolved_name = str(display_name or "").strip() or str((worker or {}).get("full_name", "") or "").strip()

    if role == ROLE_EMPLOYEE and not worker_id:
        st.error("תפקיד עובד/ת מחייב קישור לעובד/ת קיים/ת בטבלת Workers.")
        return

    actor_user_id = str(current.get("user_id", "BOOTSTRAP") or "BOOTSTRAP")
    try:
        created = create_system_user(
            st,
            id_number=id_number,
            display_name=resolved_name,
            role=role,
            worker_id=worker_id,
            created_by=actor_user_id,
            note=note,
        )
    except Exception as exc:
        st.error(str(exc))
        return

    st.success(f"המשתמש/ת {created['display_name']} נוסף/ה בהצלחה.")
    if created.get("worker_id"):
        st.caption(f"קישור לעובד: {created['worker_id']}")
    st.rerun()


def _render_edit_user(st, current: dict[str, str]) -> None:
    st.subheader("עריכת משתמש/ת והרשאה")
    try:
        users = list_users(st)
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את משתמשי המערכת: {exc}")
        return

    if not users:
        st.info("עדיין אין משתמשי מערכת.")
        return

    user_by_label: dict[str, dict[str, str]] = {}
    labels: list[str] = []
    for user in users:
        label = (
            f"{user.get('display_name', '')} - {user.get('role', '')} - "
            f"{user.get('status', '')} - {user.get('user_id', '')}"
        )
        labels.append(label)
        user_by_label[label] = user

    selected_label = st.selectbox("משתמש/ת", labels, key="tool7_edit_user_select")
    selected = user_by_label[selected_label]

    role_options = list(SYSTEM_ROLES)
    status_options = [STATUS_ACTIVE, STATUS_INACTIVE]
    current_role = selected.get("role") if selected.get("role") in role_options else ROLE_EMPLOYEE
    current_status = selected.get("status") if selected.get("status") in status_options else STATUS_ACTIVE

    with st.form("tool7_edit_user_form"):
        display_name = st.text_input("שם לתצוגה", value=selected.get("display_name", ""))
        st.text_input("ת.ז", value=selected.get("id_number", ""), disabled=True)
        role = st.selectbox("תפקיד מערכת", role_options, index=role_options.index(current_role))
        status = st.selectbox("סטטוס", status_options, index=status_options.index(current_status))
        worker_id = st.text_input(
            "Worker ID (אופציונלי)",
            value=selected.get("worker_id", ""),
            help="יש להשאיר ריק למנהל/ת שאינו/ה עובד/ת מנוהל/ת.",
        )
        note = st.text_area("הערה", value=selected.get("note", ""))
        submitted = st.form_submit_button("שמור שינויים", type="primary", width="stretch")

    if not submitted:
        return

    try:
        active_admins = active_access_admin_count(st)
    except Exception as exc:
        st.error(f"לא ניתן לבדוק את הרשאות המערכת: {exc}")
        return

    removes_access_admin = role != ROLE_ACCESS_ADMIN or status != STATUS_ACTIVE
    selected_is_active_admin = (
        selected.get("role") == ROLE_ACCESS_ADMIN and selected.get("status") == STATUS_ACTIVE
    )
    if selected_is_active_admin and removes_access_admin and active_admins <= 1:
        st.error("לא ניתן להסיר או להשבית את מנהל/ת ההרשאות הפעיל/ה האחרון/ה.")
        return

    if role == ROLE_EMPLOYEE and not str(worker_id or "").strip():
        st.error("תפקיד עובד/ת מחייב Worker ID מקושר.")
        return

    actor_user_id = str(current.get("user_id", "BOOTSTRAP") or "BOOTSTRAP")
    try:
        update_system_user(
            st,
            user_id=selected["user_id"],
            display_name=display_name,
            role=role,
            worker_id=worker_id,
            status=status,
            note=note,
            actor_user_id=actor_user_id,
        )
    except Exception as exc:
        st.error(str(exc))
        return

    st.success("המשתמש/ת וההרשאות עודכנו בהצלחה.")
    st.rerun()


def _render_users_table(st, app_module) -> None:
    st.subheader("משתמשי מערכת")
    try:
        users = list_users(st)
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את משתמשי המערכת: {exc}")
        return

    rows = [
        {
            "User ID": user.get("user_id", ""),
            "שם": user.get("display_name", ""),
            "תפקיד מערכת": user.get("role", ""),
            "Worker ID": user.get("worker_id", ""),
            "סטטוס": user.get("status", ""),
            "נוצר בתאריך": user.get("created_at", ""),
            "נוצר על ידי": user.get("created_by", ""),
            "עודכן לאחרונה": user.get("updated_at", ""),
        }
        for user in users
    ]
    if not rows:
        st.info("עדיין אין משתמשי מערכת.")
        return
    st.dataframe(app_module.pd.DataFrame(rows), width="stretch", hide_index=True)


def _render_access_log(st, app_module) -> None:
    st.subheader("לוג כניסות")
    st.caption("הלוג מתעד כניסות למערכת. סיסמאות ותעודות זהות אינן נשמרות בלוג.")
    try:
        rows = read_access_log(st, limit=250)
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את לוג הכניסות: {exc}")
        return
    visible = [
        {
            "תאריך ושעת כניסה": row.get("תאריך ושעת כניסה", ""),
            "User ID": row.get("User ID", ""),
            "Worker ID": row.get("Worker ID", ""),
            "שם": row.get("שם", ""),
            "סוג כניסה": row.get("סוג כניסה", ""),
            "תוצאה": row.get("תוצאה", ""),
        }
        for row in rows
    ]
    if not visible:
        st.info("עדיין אין רשומות כניסה.")
        return
    st.dataframe(app_module.pd.DataFrame(visible), width="stretch", hide_index=True)


def _render_audit_log(st, app_module) -> None:
    st.subheader("Audit Log")
    st.caption("תיעוד פעולות ניהול משמעותיות כגון יצירה ושינוי הרשאות.")
    try:
        rows = read_audit_log(st, limit=250)
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את ה-Audit Log: {exc}")
        return
    visible = [
        {
            "תאריך ושעה": row.get("תאריך ושעה", ""),
            "User ID": row.get("User ID", ""),
            "פעולה": row.get("פעולה", ""),
            "סוג יעד": row.get("סוג יעד", ""),
            "מזהה יעד": row.get("מזהה יעד", ""),
            "פרטים": row.get("פרטים", ""),
        }
        for row in rows
    ]
    if not visible:
        st.info("עדיין אין פעולות מתועדות.")
        return
    st.dataframe(app_module.pd.DataFrame(visible), width="stretch", hide_index=True)


def render(app_module) -> None:
    st = app_module.st
    current = _current_manager(st)

    app_module.render_header(
        "7. משתמשים והרשאות",
        "ניהול משתמשי מערכת, הרשאות מנהלים ותיעוד כניסות ושינויים.",
    )

    if not _can_manage_permissions(st, current):
        st.error("אין לך הרשאה לניהול משתמשים והרשאות. נדרשת הרשאת מנהל/ת הרשאות.")
        return

    if current.get("bootstrap"):
        st.warning(
            "המערכת נמצאת במצב הקמה ראשונית. יש להוסיף מנהל/ת הרשאות פעיל/ה לפני יציאה מהמערכת."
        )
    elif current.get("role") == ROLE_MANAGER:
        st.warning(
            "לא קיים כרגע מנהל/ת הרשאות פעיל/ה, ולכן נפתחה הרשאת שחזור למנהל/ת מערכת. "
            "יש להגדיר מנהל/ת הרשאות פעיל/ה."
        )

    st.caption(
        f"מחובר/ת: {current.get('display_name', 'הקמה ראשונית')} | "
        f"תפקיד: {current.get('role', ROLE_ACCESS_ADMIN)}"
    )

    users_tab, access_tab, audit_tab = st.tabs(["משתמשים והרשאות", "לוג כניסות", "Audit Log"])

    with users_tab:
        action = st.radio(
            "פעולה",
            ["הוספת משתמש/ת", "עריכת משתמש/ת", "צפייה ברשימה"],
            horizontal=True,
            key="tool7_user_action",
        )
        st.divider()
        if action == "הוספת משתמש/ת":
            _render_add_user(st, current)
        elif action == "עריכת משתמש/ת":
            _render_edit_user(st, current)
        else:
            _render_users_table(st, app_module)

    with access_tab:
        _render_access_log(st, app_module)

    with audit_tab:
        _render_audit_log(st, app_module)
