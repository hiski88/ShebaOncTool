from final_schedule_reader import select_latest_final_schedule


def test_select_latest_final_schedule_uses_highest_version():
    files = [
        {"id": "a", "name": "2026-10_V1.xlsx", "modifiedTime": "2026-09-01T10:00:00Z"},
        {"id": "b", "name": "2026-10_V3.xlsx", "modifiedTime": "2026-09-03T10:00:00Z"},
        {"id": "c", "name": "2026-10_V2_final.xls", "modifiedTime": "2026-09-04T10:00:00Z"},
        {"id": "d", "name": "2026-11_V9.xlsx", "modifiedTime": "2026-09-05T10:00:00Z"},
        {"id": "e", "name": "notes.xlsx", "modifiedTime": "2026-09-06T10:00:00Z"},
    ]

    selected = select_latest_final_schedule(files, 2026, 10)

    assert selected is not None
    assert selected["id"] == "b"
    assert selected["version"] == 3
    assert selected["year"] == 2026
    assert selected["month"] == 10


def test_select_latest_final_schedule_returns_none_when_month_missing():
    files = [{"id": "a", "name": "2026-09_V1.xlsx"}]
    assert select_latest_final_schedule(files, 2026, 10) is None


def test_select_latest_final_schedule_tolerates_manual_suffix():
    files = [
        {"id": "a", "name": "2026-10_V4_final-reviewed.xlsx", "modifiedTime": "2026-09-07T10:00:00Z"},
        {"id": "b", "name": "2026-10_V3.xlsx", "modifiedTime": "2026-09-08T10:00:00Z"},
    ]
    selected = select_latest_final_schedule(files, 2026, 10)
    assert selected is not None
    assert selected["id"] == "a"
    assert selected["version"] == 4
