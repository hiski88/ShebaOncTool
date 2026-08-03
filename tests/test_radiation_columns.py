from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from core import load_config
from radiation_overrides import install
import excel_tools
from schedule_parser import parse_schedule, read_schedule_workbook
import schedule_parser

ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT / "config" / "oncology.json")


def test_columns_c_d_e_are_radiation_and_overrides_are_idempotent():
    columns = {
        int(item["index"]): item
        for item in CONFIG["schedule"]["columns"]
        if int(item["index"]) in {2, 3, 4}
    }
    assert set(columns) == {2, 3, 4}
    assert all(item["source_code"] == "radiation" for item in columns.values())
    assert all(item["label"] == "קרינה" for item in columns.values())
    assert [columns[index]["slot"] for index in (2, 3, 4)] == [1, 2, 3]

    install()
    first_builder = excel_tools.build_schedule_template
    first_summary = schedule_parser.summarize_schedule
    install()
    assert excel_tools.build_schedule_template is first_builder
    assert schedule_parser.summarize_schedule is first_summary

    raw = excel_tools.build_schedule_template(2026, 8, CONFIG)
    workbook = load_workbook(BytesIO(raw))
    sheet = workbook["סידור עבודה"]
    assert sheet["D3"].value == "קרינה"
    assert "D3:F3" in {str(item) for item in sheet.merged_cells.ranges}

    sheet["D4"] = "עובד א"
    sheet["E4"] = "עובד ב"
    sheet["F4"] = "עובד ג"
    buffer = BytesIO()
    workbook.save(buffer)
    parsed = read_schedule_workbook(buffer.getvalue(), "radiation.xlsx")
    records = parse_schedule(parsed, CONFIG, ["עובד א", "עובד ב", "עובד ג"])
    radiation = records[
        (records["record_type"] == "task")
        & (records["task_code"] == "radiation")
    ]
    assert set(radiation["employee"]) == {"עובד א", "עובד ב", "עובד ג"}
    assert set(schedule_parser.summarize_schedule(records)["קרינה"]) == {1}
