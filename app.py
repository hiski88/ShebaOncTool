"""Streamlit entry point for the oncology scheduling prototype."""
from radiation_overrides import install as install_radiation_overrides
from calendar_event_overrides import install as install_calendar_event_overrides

install_radiation_overrides()
install_calendar_event_overrides()

import app_v2
from calendar_reader_v2 import render_calendar_reader as render_calendar_reader_v2


def _calendar_reader(year: int, month: int):
    return render_calendar_reader_v2(year, month, app_v2.CONFIG)


app_v2.render_calendar_reader = _calendar_reader
app_v2.main()
