from datetime import date

from tool6_gantt_overrides import add_months, build_gantt_values


def test_add_months_clamps_end_of_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 1, 31), 2) == date(2026, 3, 31)


def test_gantt_months_are_anchored_to_specialization_start():
    values = build_gantt_values(
        date(2026, 1, 15),
        [
            {
                "period_type": "מחלקה",
                "start_date": date(2026, 1, 15),
                "end_date": date(2026, 2, 14),
            },
            {
                "period_type": "מחקר",
                "start_date": date(2026, 2, 15),
                "end_date": date(2026, 3, 14),
            },
        ],
        month_count=3,
    )
    assert values == ["מחלקה", "מחקר", ""]


def test_gantt_shows_framework_and_rotation_details():
    values = build_gantt_values(
        date(2026, 1, 1),
        [
            {
                "period_type": "פנימית",
                "framework": "פנימית ד",
                "subunit": "קרדיולוגיה",
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 1, 31),
            }
        ],
        month_count=1,
    )
    assert values == ["פנימית - פנימית ד - קרדיולוגיה"]


def test_gantt_does_not_repeat_identical_hierarchy_values():
    values = build_gantt_values(
        date(2026, 1, 1),
        [
            {
                "period_type": "מחקר",
                "framework": "מחקר",
                "subunit": "",
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 1, 31),
            }
        ],
        month_count=1,
    )
    assert values == ["מחקר"]


def test_gantt_combines_overlapping_period_types():
    values = build_gantt_values(
        date(2026, 1, 1),
        [
            {
                "period_type": "מחלקה",
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 1, 31),
            },
            {
                "period_type": "מחקר",
                "start_date": date(2026, 1, 10),
                "end_date": date(2026, 1, 20),
            },
        ],
        month_count=1,
    )
    assert values == ["מחלקה + מחקר"]


def test_gantt_without_specialization_start_is_blank():
    assert build_gantt_values(None, [], month_count=4) == ["", "", "", ""]
