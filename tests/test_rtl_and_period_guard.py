import pandas as pd

from rtl_table_overrides import _rtl_dataframe_value
from tool6_period_guard_overrides import (
    _period_signature_from_record,
    _period_signature_from_values,
)


def test_rtl_dataframe_reverses_display_columns_without_mutating_source():
    source = pd.DataFrame([{"שם מלא": "א", "טלפון": "1", "מסלול": "ב"}])
    shown = _rtl_dataframe_value(source)
    assert list(source.columns) == ["שם מלא", "טלפון", "מסלול"]
    assert list(shown.columns) == ["מסלול", "טלפון", "שם מלא"]


def test_period_signature_matches_sheet_record_and_new_values():
    values = [
        "PNEW",
        "W0001",
        "פנימית",
        "פנימית ד",
        "",
        "",
        "08/01/2026",
        "30/06/2026",
        "",
        "13/09/2026 17:00:00",
    ]
    record = {
        "period_id": "POLD",
        "worker_id": "W0001",
        "period_type": "פנימית",
        "framework": "פנימית ד",
        "subunit": "",
        "location": "",
        "start_date": pd.Timestamp("2026-01-08").date(),
        "end_date": pd.Timestamp("2026-06-30").date(),
        "note": "",
        "updated_at": "13/09/2026 16:11",
    }
    assert _period_signature_from_values(values) == _period_signature_from_record(record)
