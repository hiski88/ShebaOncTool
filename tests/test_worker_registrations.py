from datetime import date

from worker_registrations import (
    STATUS_PENDING,
    validate_registration_fields,
)


def _valid_kwargs():
    return {
        "id_number": "123456789",
        "first_name": "ישראל",
        "last_name": "ישראלי",
        "birth_date": date(1990, 1, 2),
        "address": "רחוב 1",
        "locality": "רמת גן",
        "phone": "0501234567",
        "email": "person@example.com",
        "marital_status": "מעדיף/ה לא לציין",
        "children": "0",
    }


def test_valid_self_registration_fields_pass():
    assert validate_registration_fields(**_valid_kwargs()) is None


def test_self_registration_requires_valid_email():
    values = _valid_kwargs()
    values["email"] = "not-an-email"
    assert validate_registration_fields(**values) == "כתובת האימייל אינה בפורמט תקין."


def test_self_registration_requires_personal_fields():
    values = _valid_kwargs()
    values["first_name"] = ""
    assert validate_registration_fields(**values) == "יש להזין שם פרטי."


def test_pending_status_label_is_stable():
    assert STATUS_PENDING == "ממתין לאישור"
