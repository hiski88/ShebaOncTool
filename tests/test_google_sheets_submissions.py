from __future__ import annotations

from datetime import date

import pandas as pd

import google_sheets_submissions as submissions


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
        return _Request(
            {
                "updates": {
                    "updatedRange": "'Submissions'!A7:H7",
                    "updatedData": {"values": [values]},
                }
            }
        )

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


def test_submit_preferences_uses_single_atomic_append(monkeypatch):
    values_api = _ValuesApi()
    service = _Service(values_api)
    monkeypatch.setattr(
        submissions,
        "_service",
        lambda _st: (service, "spreadsheet-id", "Submissions"),
    )

    edited = pd.DataFrame(
        [
            {
                "תאריך": date(2026, 10, 5),
                "חסימת תורנות מלאה": True,
                "חסימת תורנות חצי": False,
                "חופש": False,
                "מעוניין בתורנות": True,
            }
        ]
    )

    stored = submissions.submit_preferences(
        object(),
        "עובד בדיקה",
        2026,
        10,
        edited,
        general_note="בדיקה",
    )

    assert len(values_api.append_calls) == 1
    call = values_api.append_calls[0]
    assert call["range"] == "'Submissions'!A:H"
    assert call["insertDataOption"] == "INSERT_ROWS"
    assert call["includeValuesInResponse"] is True
    assert call["body"]["values"][0] == stored


def test_read_submissions_sorts_newest_first(monkeypatch):
    values_api = _ValuesApi(
        read_rows=[
            ["01.10.2026 08:00:00", "ישן", "2026-10", "", "", "", "", ""],
            ["03.10.2026 08:00:00", "חדש", "2026-10", "", "", "", "", ""],
            ["02.10.2026 08:00:00", "אמצע", "2026-10", "", "", "", "", ""],
        ]
    )
    service = _Service(values_api)
    monkeypatch.setattr(
        submissions,
        "_service",
        lambda _st: (service, "spreadsheet-id", "Submissions"),
    )

    result = submissions.read_submissions(object(), 2026, 10)

    assert [row["שם עובד"] for row in result] == ["חדש", "אמצע", "ישן"]
