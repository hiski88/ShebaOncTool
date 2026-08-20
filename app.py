"""Streamlit entry point for the oncology scheduling prototype."""
from radiation_overrides import install as install_radiation_overrides
from calendar_event_overrides import install as install_calendar_event_overrides

install_radiation_overrides()
install_calendar_event_overrides()

import app_v2
from calendar_reader_v2 import render_calendar_reader as render_calendar_reader_v2
from calendar_time_overrides import install as install_calendar_time_overrides
from google_calendar import handle_oauth_callback
from preferences_output_overrides import install as install_preferences_output_overrides
from tool3_minimal_overrides import install as install_tool3_minimal_overrides
from ui_overrides import install as install_ui_overrides


# OAuth callbacks must be handled from the Streamlit entry point itself.
# app_v2 is an imported module and may stay cached between reruns, so callback
# handling at module-import time is not reliable after returning from Google.
connected, callback_error = handle_oauth_callback(app_v2.st)
if callback_error:
    app_v2.st.error(callback_error)
elif connected:
    app_v2.st.session_state["google_oauth_connected_notice"] = True


def _calendar_reader(year: int, month: int):
    if app_v2.st.session_state.pop("google_oauth_connected_notice", False):
        app_v2.st.success("החיבור ל-Google Calendar הושלם. כעת בחר יומן ולחץ על טעינה.")
    return render_calendar_reader_v2(year, month, app_v2.CONFIG)


app_v2.render_calendar_reader = _calendar_reader
install_ui_overrides(app_v2)
install_preferences_output_overrides(app_v2)
install_tool3_minimal_overrides(app_v2)
install_calendar_time_overrides(app_v2)
app_v2.main()
