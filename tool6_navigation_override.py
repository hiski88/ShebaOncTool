"""Add Tool 6 while reusing the existing navigation and manager gate."""
from __future__ import annotations


def install(app_module) -> None:
    if getattr(app_module, "_tool6_navigation_installed", False):
        return

    previous_main = app_module.main

    def _run_existing_tool(selected_tool: str) -> None:
        sidebar = app_module.st.sidebar
        original_radio = sidebar.radio

        def fixed_radio(*args, **kwargs):
            return selected_tool

        sidebar.radio = fixed_radio
        try:
            previous_main()
        finally:
            sidebar.radio = original_radio

    def main_with_tool6() -> None:
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
                "6. ניהול עובדים",
            ],
            key="tool_navigation_with_workers",
        )

        if tool != "6. ניהול עובדים":
            _run_existing_tool(tool)
            return

        if not st.session_state.get("manager_tools_authenticated", False):
            # Reuse the existing Tool 2 manager-access flow. After a successful
            # sign-in Streamlit reruns, the selection remains on Tool 6.
            _run_existing_tool("2. מתכנן")
            return

        from tool6_workers import render

        render(app_module)

    app_module.main = main_with_tool6
    app_module._tool6_navigation_installed = True
