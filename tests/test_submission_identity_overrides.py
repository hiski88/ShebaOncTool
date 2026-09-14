from __future__ import annotations

from datetime import date

import pandas as pd

import google_sheets_submissions as submissions
from submission_identity_overrides import (
    read_submissions_with_identity,
    submit_preferences_with_identity,
)


class _Request:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _ValuesApi:
    def __init__(self, read_rows=None):
        self.read_rows = read_rows or []
        self.append_calls = []

    def append(self, **kwargs):
        self.append_calls.append(kwargs)
        values = kwargs["body"]["values"][0]
        return _Request({"updates": {"updatedRange": "'Submissions'!A7:I7", "updatedData": {"values": [values]}}})

    def get(self, **kwargs):
        return _Request({"values": self.read_rows})


class _SpreadsheetsApi:
    def __init__(self, values_api):
        self._values_api = values_api

    def values(self):
        return self._values_api


class _Service:
    def __init__(self, values_api):
        self._spreadsheets_api = _SpreadsheetsApi(values_api)

    def spreadsheets(self):
        return self._spreadsheets_api


class _St:
    def __init__(self):
        self.session_state = {"medstaff_identified_worker_v1": {"worker_id": "W0042"}}


def test_submission_appends_worker_id(monkeypatch):
    values_api = _ValuesApi()
    service = _Service(values_api)
    monkeypatch.setattr(submissions, "_service", lambda _st: (service, "spreadsheet-id", "Submissions"))
    edited = pd.DataFrame([
        {
            "תאריך": date(2026, 10, 5),
            "חסימת תורנות מלאה": True,
            "חסימת תורנות חצי": False,
            "חופש": False,
            "מעוניין בתורנות": False,
        }
    ])

    stored = submit_preferences_with_identity(_St(), "עובד בדיקה", 2026, 10, edited)

    assert values_api.append_calls[0]["range"] == "'Submissions'!A:I"
    assert stored[-1] == "W0042"


def test_read_submission_keeps_legacy_blank_worker_id(monkeypatch):
    values_api = _ValuesApi(read_rows=[
        ["01.10.2026 08:00:00", "ישן", "2026-10", "", "", "", "", ""],
        ["02.10.2026 08:00:00", "חדש", "2026-10", "", "", "", "", "", "W0002"],
    ])
    service = _Service(values_api)
    monkeypatch.setattr(submissions, "_service", lambda _st: (service, "spreadsheet-id", "Submissions"))

    result = read_submissions_with_identity(object(), 2026, 10)

    assert result[0]["Worker ID"] == "W0002"
    assert result[1]["Worker ID"] == ""
