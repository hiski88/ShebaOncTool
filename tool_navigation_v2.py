"""Application tool navigation and shared access gates.

Access policy:
- Tool 1 is the employee preference tool.
- Tools 2-3 and 6-7 are management tools.
- Tools 4-5 are staff tools.
- The entry flow authenticates managers before this navigation is shown.

Passwords are read only from Streamlit Secrets and are never stored in code.
"""
from __future__ import annotations


MANAGER_PASSWORD_SECRET = "MANAGER_TOOLS_PASSWORD"
STAFF_PASSWORD_SECRET = "STAFF_TOOLS_PASSWORD"


def _password_granted(st, *, secret_name: str, session_key: str, heading: str, widget_prefix: str) -> bool:
    if st.session_state.get(session_key, False):
        return True

    try:
        if secret_name not in st.secrets:
            st.error(f"סיסמת הגישה לכלי זה אינה מוגדרת באפליקציה ({secret_name}).")
            return False
        expected_password = str(st.secrets[secret_name] or "")
    except Exception as exc:
        st.error(f"לא ניתן לקרוא את סיסמת הגישה ({secret_name}): {exc}")
        return False

    if not expected_password:
        st.error(f"סיסמת הגישה לכלי זה ריקה ({secret_name}).")
        return False

    st.subheader(heading)
    password_col, _ = st.columns([1, 5])
    with password_col:
        entered = st.text_input(
            "סיסמה",
            type="password",
            key=f"{widget_prefix}_password_input",
        )
        login_clicked = st.button(
            "כניסה",
            type="primary",
            width="stretch",
            key=f"{widget_prefix}_login",
        )
    if login_clicked:
        if entered == expected_password:
            st.session_state[session_key] = True
            st.rerun()
        else:
            st.error("סיסמה שגויה.")
    return False


def install(app_module) -> None:
    if getattr(app_module, "_tool_navigation_v2_installed", False):
        return

    original_tool_manager = app_module.tool_manager
    original_tool_calendar = app_module.tool_calendar

    def tool_final_schedule_upload() -> None:
        from tool3_final_schedule import render

        render(app_module)

    def tool_historical_placeholder() -> None:
        st = app_module.st
        app_module.render_header(
            "5. נתונים היסטוריים והוגנות",
            "צפייה בנתונים היסטוריים, עומסים והוגנות לאורך זמן.",
        )
        st.info("כלי הנתונים ההיסטוריים וההוגנות ייבנה בשלב האחרון.")

    def tool_workers() -> None:
        from tool6_workers import render

        render(app_module)

    def tool_system_users() -> None:
        from tool7_system_users import render

        render(app_module)

    def main_tools() -> None:
        st = app_module.st
        st.sidebar.title("כלי המערכת")
        tool = st.sidebar.radio(
            "בחירת כלי",
            [
                "1. הזנת העדפות",
                "2. מתכנן",
                "3. לו״ז חודשי",
                "4. יצירת זימון ליומן",
                "5. נתונים היסטוריים והוגנות",
                "6. ניהול עובדים",
                "7. משתמשים והרשאות",
            ],
        )

        if tool == "1. הזנת העדפות":
            app_module.tool_preferences()
            return

        if tool == "2. מתכנן":
            if not _password_granted(
                st,
                secret_name=MANAGER_PASSWORD_SECRET,
                session_key="manager_tools_authenticated",
                heading="גישה לכלי המתכנן",
                widget_prefix="manager_tools",
            ):
                return
            st.session_state["tool2_planner_authenticated"] = True
            original_tool_manager()
            return

        if tool == "3. לו״ז חודשי":
            if not _password_granted(
                st,
                secret_name=MANAGER_PASSWORD_SECRET,
                session_key="manager_tools_authenticated",
                heading="גישה לכלי המתכנן",
                widget_prefix="manager_tools",
            ):
                return
            tool_final_schedule_upload()
            return

        if tool == "4. יצירת זימון ליומן":
            if not _password_granted(
                st,
                secret_name=STAFF_PASSWORD_SECRET,
                session_key="staff_tools_authenticated",
                heading="גישה לכלי הצוות",
                widget_prefix="staff_tools",
            ):
                return
            original_tool_calendar()
            return

        if tool == "5. נתונים היסטוריים והוגנות":
            if not _password_granted(
                st,
                secret_name=STAFF_PASSWORD_SECRET,
                session_key="staff_tools_authenticated",
                heading="גישה לכלי הצוות",
                widget_prefix="staff_tools",
            ):
                return
            tool_historical_placeholder()
            return

        if tool == "6. ניהול עובדים":
            if not _password_granted(
                st,
                secret_name=MANAGER_PASSWORD_SECRET,
                session_key="manager_tools_authenticated",
                heading="גישה לניהול עובדים",
                widget_prefix="manager_tools",
            ):
                return
            tool_workers()
            return

        if not _password_granted(
            st,
            secret_name=MANAGER_PASSWORD_SECRET,
            session_key="manager_tools_authenticated",
            heading="גישה למשתמשים והרשאות",
            widget_prefix="manager_tools",
        ):
            return
        tool_system_users()

    app_module.main = main_tools
    app_module._tool_navigation_v2_installed = True
