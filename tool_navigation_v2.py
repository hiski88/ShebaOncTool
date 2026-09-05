"""Five-tool navigation and shared access gates.

Access policy:
- Tool 1 is public to staff.
- Tools 2-3 share the manager password.
- Tools 4-5 share the staff password.

Passwords are read only from Streamlit Secrets and are never stored in code.
"""
from __future__ import annotations


MANAGER_PASSWORD_SECRET = "MANAGER_TOOLS_PASSWORD"
STAFF_PASSWORD_SECRET = "STAFF_TOOLS_PASSWORD"


def _password_granted(st, *, secret_name: str, session_key: str, heading: str, widget_prefix: str) -> bool:
    if st.session_state.get(session_key, False):
        return True

    try:
        expected_password = str(st.secrets.get(secret_name, "") or "")
    except Exception:
        expected_password = ""

    if not expected_password:
        st.error("סיסמת הגישה לכלי זה אינה מוגדרת באפליקציה.")
        return False

    st.subheader(heading)
    entered = st.text_input(
        "סיסמה",
        type="password",
        key=f"{widget_prefix}_password_input",
    )
    if st.button("כניסה", type="primary", key=f"{widget_prefix}_login"):
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

    def tool_final_schedule_upload_placeholder() -> None:
        st = app_module.st
        app_module.render_header(
            "3. העלאת סידור סופי",
            "כלי למתכנן לשמירת הסידור הסופי במערכת. העלאת הקובץ והקליטה למאגר ייבנו בשלב הבא.",
        )
        st.info("הכלי מוכן במבנה המערכת. בשלב הבא נוסיף העלאת קובץ, פענוח ושמירה מרכזית.")

    def tool_historical_placeholder() -> None:
        st = app_module.st
        app_module.render_header(
            "5. נתונים היסטוריים והוגנות",
            "צפייה בנתונים היסטוריים, עומסים והוגנות לאורך זמן.",
        )
        st.info("כלי הנתונים ההיסטוריים וההוגנות ייבנה בשלב האחרון.")

    def main_five_tools() -> None:
        st = app_module.st
        st.sidebar.title("כלי המערכת")
        tool = st.sidebar.radio(
            "בחירת כלי",
            [
                "1. הזנת העדפות",
                "2. מתכנן",
                "3. העלאת סידור סופי",
                "4. יצירת זימונים",
                "5. נתונים היסטוריים והוגנות",
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
            # Tool 2 already contains a legacy internal gate. Mark it as
            # authenticated after the shared manager gate so no second password
            # prompt is shown.
            st.session_state["tool2_planner_authenticated"] = True
            original_tool_manager()
            return

        if tool == "3. העלאת סידור סופי":
            if not _password_granted(
                st,
                secret_name=MANAGER_PASSWORD_SECRET,
                session_key="manager_tools_authenticated",
                heading="גישה לכלי המתכנן",
                widget_prefix="manager_tools",
            ):
                return
            tool_final_schedule_upload_placeholder()
            return

        if tool == "4. יצירת זימונים":
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

        if not _password_granted(
            st,
            secret_name=STAFF_PASSWORD_SECRET,
            session_key="staff_tools_authenticated",
            heading="גישה לכלי הצוות",
            widget_prefix="staff_tools",
        ):
            return
        tool_historical_placeholder()

    app_module.main = main_five_tools
    app_module._tool_navigation_v2_installed = True
