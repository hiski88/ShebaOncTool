from datetime import date

from tool6_workers import (
    _format_date,
    _parse_sheet_date,
    _period_records,
    _validate_period_fields,
    _validate_worker_fields,
    _worker_records,
)


def test_parse_sheet_date_supports_workers_display_format():
    assert _parse_sheet_date("13/09/2026") == date(2026, 9, 13)
    assert _parse_sheet_date("13.09.2026") == date(2026, 9, 13)
    assert _parse_sheet_date("") is None
    assert _format_date(date(2026, 9, 13)) == "13/09/2026"


def test_worker_records_preserve_sheet_row_number_and_identity():
    rows = [
        [
            "WTEST1",
            "Test",
            "Worker",
            "example-id",
            "01/02/1990",
            "Example address",
            "Example city",
            "example-phone",
            "worker@example.test",
            "נשוי/אה",
            "1",
            "אונקולוגיה רפואית",
            "פעיל",
            "מחלקה",
            "לא",
            "01/01/2026",
            "",
            "note",
            "01/01/2025",
        ]
    ]
    records = _worker_records(rows)
    assert len(records) == 1
    assert records[0]["row_number"] == 2
    assert records[0]["worker_id"] == "WTEST1"
    assert records[0]["birth_date"] == date(1990, 2, 1)
    assert records[0]["activity_end"] is None


def test_validate_worker_fields_rejects_activity_end_before_start():
    error = _validate_worker_fields(
        first_name="Test",
        last_name="Worker",
        id_number="example-id",
        birth_date=date(1990, 2, 1),
        address="Example address",
        locality="Example city",
        phone="example-phone",
        email="worker@example.test",
        marital_status="נשוי/אה",
        children="1",
        track="אונקולוגיה רפואית",
        status="פעיל",
        eligibility="מחלקה",
        basic_science_exemption="לא",
        department_start=date(2026, 1, 1),
        specialization_start=date(2025, 1, 1),
        activity_end=date(2025, 12, 31),
    )
    assert error == "תאריך סיום הפעילות לא יכול להיות מוקדם מתאריך תחילת הפעילות במחלקה."


def test_period_records_preserve_identity_and_parse_dates():
    rows = [
        [
            "PTEST1",
            "WTEST1",
            "מחלקה",
            "אונקולוגיה",
            "מחלקת אשפוז",
            "שיבא",
            "01/10/2026",
            "31/12/2026",
            "note",
            "13/09/2026 14:00:00",
        ]
    ]
    records = _period_records(rows)
    assert len(records) == 1
    assert records[0]["row_number"] == 2
    assert records[0]["period_id"] == "PTEST1"
    assert records[0]["worker_id"] == "WTEST1"
    assert records[0]["start_date"] == date(2026, 10, 1)
    assert records[0]["end_date"] == date(2026, 12, 31)


def test_validate_period_fields_rejects_invalid_range():
    error = _validate_period_fields(
        period_type="מחלקה",
        start_date=date(2026, 10, 2),
        end_date=date(2026, 10, 1),
    )
    assert error == "תאריך הסיום לא יכול להיות מוקדם מתאריך ההתחלה."


def test_validate_period_fields_requires_period_type():
    error = _validate_period_fields(
        period_type="בחר/י...",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 31),
    )
    assert error == "יש לבחור סוג תקופה."
