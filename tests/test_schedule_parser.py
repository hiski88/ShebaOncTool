from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont

from core import load_config
from excel_tools import build_schedule_template
from schedule_parser import parse_schedule, read_schedule_workbook, summarize_schedule, validate_schedule

ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / "config" / "oncology.json")


def _sample_workbook() -> bytes:
    raw = build_schedule_template(2026, 8, CONFIG)
    workbook = load_workbook(BytesIO(raw))
    sheet = workbook["סידור עבודה"]

    # 3.8.2026, row 6: a struck-out original employee, after-duty status, and replacement.
    sheet["G6"] = CellRichText(
        [
            TextBlock(InlineFont(strike=True), "עובד א"),
            "\nא\"ת\nעובד ב",
        ]
    )
    sheet["H6"] = "עובד ג"
    sheet["I6"] = "עובדת ד"
    sheet["X6"] = "עובד ג"

    # Friday 7.8.2026, row 10: duty employee plus an additional Friday visitor.
    sheet["G10"] = "עובד ג"
    sheet["H10"] = "עובד ב"
    sheet["X10"] = "עובד ג"

    # Saturday 8.8.2026, row 11: outgoing Friday duty plus Saturday duty.
    sheet["G11"] = "עובד ג"
    sheet["H11"] = "עובדת ד"
    sheet["X11"] = "עובדת ד"

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_strikethrough_replacement_and_weekend_rules():
    workbook = read_schedule_workbook(_sample_workbook(), "sample.xlsx")
    names = ["עובד א", "עובד ב", "עובד ג", "עובדת ד"]
    records = parse_schedule(workbook, CONFIG, names)

    employee_a = records[records["employee"] == "עובד א"]
    assert "after_duty" in set(employee_a["task_code"])
    assert not ((employee_a["record_type"] == "task") & (employee_a["task_code"] == "department_regular")).any()

    employee_b_day = records[(records["employee"] == "עובד ב") & (records["date"].astype(str) == "2026-08-03")]
    assert "department_regular" in set(employee_b_day["task_code"])

    friday_employee_c = records[(records["employee"] == "עובד ג") & (records["date"].astype(str) == "2026-08-07")]
    assert "department_weekend_friday_duty" in set(friday_employee_c["task_code"])
    assert "ward_duty_friday" in set(friday_employee_c["task_code"])

    friday_employee_b = records[(records["employee"] == "עובד ב") & (records["date"].astype(str) == "2026-08-07")]
    assert "friday_visit" in set(friday_employee_b["task_code"])

    saturday_employee_c = records[(records["employee"] == "עובד ג") & (records["date"].astype(str) == "2026-08-08")]
    assert "department_weekend_outgoing" in set(saturday_employee_c["task_code"])

    saturday_employee_d = records[(records["employee"] == "עובדת ד") & (records["date"].astype(str) == "2026-08-08")]
    assert "department_weekend_saturday_duty" in set(saturday_employee_d["task_code"])
    assert "ward_duty_saturday" in set(saturday_employee_d["task_code"])

    summary = summarize_schedule(records)
    employee_c_summary = summary[summary["עובד/ת"] == "עובד ג"].iloc[0]
    assert employee_c_summary["תורנות שישי"] == 1
    assert employee_c_summary["מחלקה סופ\"ש"] >= 2


def test_configurable_coverage_validation():
    workbook = read_schedule_workbook(_sample_workbook(), "sample.xlsx")
    names = ["עובד א", "עובד ב", "עובד ג", "עובדת ד"]
    records = parse_schedule(workbook, CONFIG, names)
    validation = validate_schedule(records, CONFIG)

    # The synthetic file intentionally leaves most days empty, so validation must detect gaps.
    assert not validation.empty
    assert "איוש מחלקה" in set(validation["בדיקה"])
    assert "תורן מחלקה" in set(validation["בדיקה"])
