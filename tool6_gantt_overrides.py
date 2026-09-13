"""Derived 66-month specialization overview for Tool 6.

WorkerPeriods remains the source of truth for exact dates. Workers columns
T:CG are a derived month-by-month operational overview anchored to each
worker's specialization start date.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta


GANTT_MONTH_COUNT = 66
GANTT_START_COLUMN = "T"
GANTT_END_COLUMN = "CG"
INITIAL_SYNC_SESSION_KEY = "tool6_gantt_initial_sync_v1"


def add_months(anchor: date, offset: int) -> date:
    """Move an anchor date by whole months, clamping the day when required."""
    zero_based = anchor.month - 1 + int(offset)
    year = anchor.year + zero_based // 12
    month = zero_based % 12 + 1
    day = min(anchor.day, monthrange(year, month)[1])
    return date(year, month, day)


def build_gantt_values(
    specialization_start: date | None,
    periods: list[dict[str, object]],
    month_count: int = GANTT_MONTH_COUNT,
) -> list[str]:
    """Return derived month cells from exact WorkerPeriods records.

    Month 1 starts on the exact specialization start date. Each following
    bucket starts on the corresponding day in the next month. Any period that
    overlaps a bucket contributes its period type. Multiple simultaneous period
    types are shown together and exact dates remain in WorkerPeriods.
    """
    if specialization_start is None:
        return [""] * month_count

    output: list[str] = []
    for index in range(month_count):
        bucket_start = add_months(specialization_start, index)
        bucket_end = add_months(specialization_start, index + 1) - timedelta(days=1)
        labels: list[str] = []
        for period in periods:
            period_start = period.get("start_date")
            period_end = period.get("end_date")
            period_type = str(period.get("period_type", "") or "").strip()
            if not isinstance(period_start, date) or not isinstance(period_end, date) or not period_type:
                continue
            if period_start <= bucket_end and period_end >= bucket_start and period_type not in labels:
                labels.append(period_type)
        output.append(" + ".join(labels))
    return output


def _pad_gantt_row(values: list[object]) -> list[str]:
    row = [str(value or "") for value in values[:GANTT_MONTH_COUNT]]
    return row + [""] * (GANTT_MONTH_COUNT - len(row))


def _worker_expected_values(tool6, worker: dict[str, object], periods: list[dict[str, object]]) -> list[str]:
    worker_id = str(worker.get("worker_id", "") or "")
    worker_periods = [period for period in periods if str(period.get("worker_id", "")) == worker_id]
    worker_periods.sort(
        key=lambda item: (
            item.get("start_date") or date.min,
            item.get("end_date") or date.min,
            str(item.get("period_type", "")),
        )
    )
    return build_gantt_values(worker.get("specialization_start"), worker_periods)


def sync_worker_gantt(st, worker_id: str) -> bool:
    """Synchronize one Workers T:CG row. Returns True only when a write occurred."""
    import tool6_workers as tool6

    wanted = str(worker_id or "").strip()
    workers = tool6._worker_records(tool6._read_worker_rows(st))
    worker = next((item for item in workers if str(item.get("worker_id", "")) == wanted), None)
    if worker is None:
        return False

    periods = tool6._period_records(tool6._read_period_rows(st))
    expected = _worker_expected_values(tool6, worker, periods)
    row_number = int(worker["row_number"])

    service, spreadsheet_id = tool6._workers_service(st)
    current_response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{tool6.WORKERS_SHEET}'!{GANTT_START_COLUMN}{row_number}:{GANTT_END_COLUMN}{row_number}",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    current_rows = current_response.get("values", [])
    current = _pad_gantt_row(current_rows[0] if current_rows else [])
    if current == expected:
        return False

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tool6.WORKERS_SHEET}'!{GANTT_START_COLUMN}{row_number}:{GANTT_END_COLUMN}{row_number}",
        valueInputOption="RAW",
        body={"values": [expected]},
    ).execute()
    return True


def sync_all_worker_gantts(st) -> int:
    """Synchronize all current workers efficiently and return number of changed rows."""
    import tool6_workers as tool6

    workers = tool6._worker_records(tool6._read_worker_rows(st))
    periods = tool6._period_records(tool6._read_period_rows(st))
    if not workers:
        return 0

    service, spreadsheet_id = tool6._workers_service(st)
    current_response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{tool6.WORKERS_SHEET}'!{GANTT_START_COLUMN}2:{GANTT_END_COLUMN}501",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    current_rows = current_response.get("values", [])

    updates = []
    for worker in workers:
        row_number = int(worker["row_number"])
        expected = _worker_expected_values(tool6, worker, periods)
        current_index = row_number - 2
        raw_current = current_rows[current_index] if 0 <= current_index < len(current_rows) else []
        current = _pad_gantt_row(raw_current)
        if current == expected:
            continue
        updates.append(
            {
                "range": (
                    f"'{tool6.WORKERS_SHEET}'!{GANTT_START_COLUMN}{row_number}:"
                    f"{GANTT_END_COLUMN}{row_number}"
                ),
                "values": [expected],
            }
        )

    if updates:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()
    return len(updates)


def install(app_module) -> None:
    import tool6_workers as tool6

    if getattr(tool6, "_tool6_gantt_overrides_installed", False):
        return

    original_append_period = tool6._append_period
    original_update_period_row = tool6._update_period_row
    original_update_worker_row = tool6._update_worker_row
    original_render = tool6.render

    def append_period_with_gantt(st, values: list[str]) -> None:
        original_append_period(st, values)
        if len(values) > 1:
            sync_worker_gantt(st, values[1])

    def update_period_with_gantt(st, row_number: int, values: list[str]) -> None:
        original_update_period_row(st, row_number, values)
        if len(values) > 1:
            sync_worker_gantt(st, values[1])

    def update_worker_with_gantt(st, row_number: int, values: list[str]) -> None:
        original_update_worker_row(st, row_number, values)
        if values:
            sync_worker_gantt(st, values[0])

    def render_with_initial_sync(module) -> None:
        st = module.st
        if not st.session_state.get(INITIAL_SYNC_SESSION_KEY):
            try:
                sync_all_worker_gantts(st)
            except Exception as exc:
                st.warning(f"לא ניתן לרענן כרגע את תצוגת 66 החודשים: {exc}")
            finally:
                st.session_state[INITIAL_SYNC_SESSION_KEY] = True
        original_render(module)

    tool6._append_period = append_period_with_gantt
    tool6._update_period_row = update_period_with_gantt
    tool6._update_worker_row = update_worker_with_gantt
    tool6.render = render_with_initial_sync
    tool6._tool6_gantt_overrides_installed = True
