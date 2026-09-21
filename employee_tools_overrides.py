"""Employee-mode navigation for personal MedStaff tools."""
from __future__ import annotations

import entry_flow


EMPLOYEE_TOOL_KEY = "medstaff_employee_tool_v1"


def _render_employee_tools(st, app_module) -> None:
    entry_flow._hide_sidebar(st)
    worker = st.session_state.get(entry_flow.IDENTIFIED_WORKER_KEY)
    if not isinstance(worker, dict) or not worker.get("worker_id"):
        st.session_state.pop(entry_flow.IDENTIFIED_WORKER_KEY, None)
        st.session_state[entry_flow.ENTRY_MODE_KEY] = "employee"
        st.rerun()

    top_left, top_right = st.columns([5, 1])
    with top_left:
        st.caption(f"מחובר/ת כ-{worker.get('full_name', '')}")
    with top_right:
        if st.button("החלפת משתמש", width="stretch", key="employee_logout_v1"):
            entry_flow._clear_entry_state(st)
            st.session_state.pop(EMPLOYEE_TOOL_KEY, None)
            st.rerun()

    tool = st.radio(
        "כלים אישיים",
        ["הזנת העדפות", "לו״ז חודשי", "יצירת זימון ליומן"],
        horizontal=True,
        key=EMPLOYEE_TOOL_KEY,
    )
    st.divider()

    st.session_state["preferences_employee"] = str(worker.get("full_name", ""))
    if tool == "הזנת העדפות":
        app_module.tool_preferences()
        return
    if tool == "לו״ז חודשי":
        from tool3_final_schedule import render as render_monthly_schedule

        render_monthly_schedule(app_module)
        return
    app_module.tool_calendar()


def install(app_module) -> None:
    """Patch employee mode after Tool 4 has its final central/time behavior."""
    if getattr(entry_flow, "_employee_tools_override_installed", False):
        return
    entry_flow._render_employee_tool = lambda st, module: _render_employee_tools(st, module)
    entry_flow._employee_tools_override_installed = True
