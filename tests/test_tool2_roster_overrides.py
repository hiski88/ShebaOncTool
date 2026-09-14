from datetime import date

from tool2_roster_overrides import (
    _is_active_for_month,
    _latest_submissions_by_worker,
    _worker_period_summary,
)


def test_active_worker_respects_department_dates():
    worker = {
        "status": "פעיל",
        "department_start": date(2026, 10, 5),
        "activity_end": None,
    }
    assert _is_active_for_month(worker, 2026, 10) is True
    assert _is_active_for_month(worker, 2026, 9) is False


def test_period_summary_includes_rotation_details():
    periods = [
        {
            "worker_id": "W0001",
            "period_type": "פנימית",
            "framework": "פנימית ד",
            "subunit": "",
            "start_date": date(2026, 9, 1),
            "end_date": date(2026, 10, 15),
        }
    ]
    assert _worker_period_summary("W0001", periods, 2026, 10) == "פנימית - פנימית ד"


def test_latest_submission_prefers_worker_id_and_counts_duplicates():
    roster = [{"worker_id": "W0001", "first_name": "יאיר", "last_name": "כהן"}]
    rows = [
        {"Worker ID": "W0001", "שם עובד": "שם חדש", "זמן הגשה": "02.10.2026"},
        {"Worker ID": "W0001", "שם עובד": "שם ישן", "זמן הגשה": "01.10.2026"},
    ]
    latest, counts = _latest_submissions_by_worker(rows, roster)
    assert latest["W0001"]["שם עובד"] == "שם חדש"
    assert counts["W0001"] == 2
