from datetime import date
from pathlib import Path

import pandas as pd

from core import (
    availability_matrix,
    build_month_table,
    build_submission,
    decode_submission,
    encode_submission,
    important_day_name,
    load_config,
    records_to_events,
)


def test_month_table_has_all_august_days():
    table = build_month_table(2026, 8)
    assert len(table) == 31
    assert table.iloc[0]["תאריך"] == date(2026, 8, 1)
    assert table.iloc[-1]["תאריך"] == date(2026, 8, 31)
    assert table.iloc[-1]["יום"] == "ב"


def test_rosh_hashana_and_erev_are_detected():
    assert "ערב ראש השנה" in important_day_name(date(2026, 9, 11))
    assert "ראש השנה" in important_day_name(date(2026, 9, 12))


def test_chol_hamoed_is_labeled_separately():
    assert important_day_name(date(2026, 9, 26)) == "סוכות"
    assert important_day_name(date(2026, 9, 27)) == "חול המועד סוכות"
    assert important_day_name(date(2026, 10, 2)).startswith("הושענא רבה")


def test_submission_round_trip_and_matrix():
    table = build_month_table(2026, 8)
    table["לא זמין"] = False
    table["חופש"] = False
    table["הערה"] = ""
    table.loc[0, "לא זמין"] = True
    table.loc[1, "חופש"] = True
    table.loc[1, "הערה"] = "כנס"

    payload = build_submission("עובד לדוגמה", 2026, 8, table)
    decoded = decode_submission(encode_submission(payload))
    assert decoded == payload

    matrix = availability_matrix([decoded], 2026, 8)
    assert matrix.loc[0, "עובד לדוגמה"] == "לא זמין"
    assert matrix.loc[1, "עובד לדוגמה"] == "חופש | כנס"


def test_weekend_department_roles_do_not_duplicate_duty_events():
    config = load_config(Path(__file__).resolve().parents[1] / "config" / "oncology.json")
    records = pd.DataFrame(
        [
            {
                "date": date(2026, 8, 7),
                "employee": "עובד לדוגמה",
                "record_type": "task",
                "task_code": "department_weekend_friday_duty",
                "task_label": "מחלקה סופש",
                "subtype": "",
                "source_cell": "G10",
            },
            {
                "date": date(2026, 8, 7),
                "employee": "עובד לדוגמה",
                "record_type": "task",
                "task_code": "ward_duty_friday",
                "task_label": "תורנות שישי",
                "subtype": "",
                "source_cell": "X10",
            },
        ]
    )
    events = records_to_events(records, "עובד לדוגמה", config)
    assert [event.task_code for event in events] == ["ward_duty_friday"]
