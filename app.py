"""Streamlit entry point for the oncology scheduling prototype."""
from radiation_overrides import install as install_radiation_overrides
from calendar_event_overrides import install as install_calendar_event_overrides

install_radiation_overrides()
install_calendar_event_overrides()

import app_v2
from calendar_reader_v2 import render_calendar_reader as render_calendar_reader_v2
from calendar_time_overrides import install as install_calendar_time_overrides
from employee_registration_overrides import install as install_employee_registration_overrides
from entry_flow import install as install_entry_flow
from google_calendar import handle_oauth_callback
from month_selector_timezone_overrides import install as install_month_selector_timezone_overrides
from preferences_output_overrides import install as install_preferences_output_overrides
from preferences_privacy_overrides import install as install_preferences_privacy_overrides
from rtl_table_overrides import install as install_rtl_table_overrides
from schedule_layout_overrides import install as install_schedule_layout_overrides
from special_days_engine import install as install_special_days_engine
from submission_identity_overrides import install as install_submission_identity_overrides
from system_role_labels_overrides import install as install_system_role_labels_overrides
from tool1_preferences_mvp_overrides import install as install_tool1_preferences_mvp_overrides
from tool2_roster_overrides import install as install_tool2_roster_overrides
from tool2_submissions_overrides import install as install_tool2_submissions_overrides
from tool3_minimal_overrides import install as install_tool3_minimal_overrides
from tool4_central_schedule_overrides import install as install_tool4_central_schedule_overrides
from tool6_gantt_overrides import install as install_tool6_gantt_overrides
from tool6_period_guard_overrides import install as install_tool6_period_guard_overrides
from tool6_registration_overrides import install as install_tool6_registration_overrides
from tool_navigation_v2 import install as install_tool_navigation_v2
from ui_overrides import install as install_ui_overrides


# app_v2 still contains the legacy callback handler. If it already handled the
# OAuth return, it clears the query parameters. Only run the entry-point
# fallback when a code is still present, which avoids redeeming the same Google
# authorization code twice (invalid_grant).
if app_v2.st.query_params.get("code"):
    app_v2.st.session_state.pop("google_oauth_state", None)
    _, callback_error = handle_oauth_callback(app_v2.st)
    if callback_error:
        app_v2.st.error(callback_error)


def _calendar_reader(year: int, month: int):
    return render_calendar_reader_v2(year, month, app_v2.CONFIG)


app_v2.render_calendar_reader = _calendar_reader
install_ui_overrides(app_v2)
# Read-only tables are rendered from right to left throughout the Hebrew UI.
install_rtl_table_overrides(app_v2)
# One central source/filter engine must be installed before Tools 1/2/3 so all
# of them see the same holiday / special-day labels.
install_special_days_engine(app_v2)
# Month defaults must be based on Israel local time rather than the server date.
install_month_selector_timezone_overrides(app_v2)
# Install the expanded Tool 1 editor first. Output and private-persistence
# wrappers then capture the new fields without changing the underlying model.
install_tool1_preferences_mvp_overrides(app_v2)
# Attach stable Worker ID to new submissions before Tool 1 output and Tool 2
# capture the submission helpers imported from google_sheets_submissions.
install_submission_identity_overrides(app_v2)
install_preferences_output_overrides(app_v2)
install_preferences_privacy_overrides(app_v2)
install_tool2_submissions_overrides(app_v2)
# Workers is the source of truth for Tool 2; monthly submissions enrich the
# active roster rather than defining who exists in the planning population.
install_tool2_roster_overrides(app_v2)
# The calendar tool must understand both the legacy schedule layout and the
# newer layout with a holiday/special-day column before it infers names or
# parses duties.
install_schedule_layout_overrides(app_v2)
# Tool 4 starts from the existing parser/event logic, then swaps manual upload
# for the latest central final schedule. The time wrapper must be installed last
# so users can still adjust duty hours for the centrally loaded schedule.
install_tool3_minimal_overrides(app_v2)
install_tool4_central_schedule_overrides(app_v2)
install_calendar_time_overrides(app_v2)
# Extend Tool 6 with manager review before the Gantt wrapper captures its
# renderer, so the initial Gantt sync still runs for every Tool 6 screen.
install_tool6_registration_overrides(app_v2)
# Keep WorkerPeriods as the exact-date source of truth and derive the 66-month
# Workers overview automatically whenever Tool 6 data changes.
install_tool6_gantt_overrides(app_v2)
# Guard after the Gantt wrapper so duplicate checks happen before any write or
# derived-month synchronization.
install_tool6_period_guard_overrides(app_v2)
# Normalize the legacy permission-admin role to its clearer UI label while
# remaining backward compatible with already stored SystemUsers rows.
install_system_role_labels_overrides(app_v2)
# Install tool navigation first. Then extend employee identification with
# self-registration before entry_flow captures the final login renderer.
install_tool_navigation_v2(app_v2)
install_employee_registration_overrides(app_v2)
install_entry_flow(app_v2)
app_v2.main()
