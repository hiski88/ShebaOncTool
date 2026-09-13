from datetime import date

from tool6_workers import _parse_sheet_date, _validate_worker_fields, _worker_records


def test_parse_sheet_date_supports_workers_display_format():
    assert _parse_sheet_date("13/09/2026") == date(2026, 9, 13)
    assert _parse_sheet_date("13.09.2026") == date(2026, 9, 13)
    assert _parse_sheet_date("") is None


def test_worker_records_preserve_sheet_row_number_and_identity():
    rows = [
        [
            "W0001",
            "Yael",
            "Cohen",
            "123456789",
            "01/02/1990",
            "Street 1",
            "Ramat Gan",
            "0500000000",
            "yael@example.com",
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
    assert records[0]["worker_id"] == "W0001"
    assert records[0]["birth_date"] == date(1990, 2, 1)
    assert records[0]["activity_end"] is None


def test_validate_worker_fields_rejects_activity_end_before_start():
    error = _validate_worker_fields(
        first_name="Yael",
        last_name="Cohen",
        id_number="123456789",
        birth_date=date(1990, 2, 1),
        address="Street 1",
        locality="Ramat Gan",
        phone="0500000000",
        email="yael@example.com",
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
