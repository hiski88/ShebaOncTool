from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd
from pyluach import dates as hebrew_dates

SUBMISSION_MARKER = "MEDSTAFF_ONC_V1"
HEBREW_WEEKDAYS = ["ב", "ג", "ד", "ה", "ו", "ש", "א"]
HEBREW_MONTHS = {
    1: "ינואר", 2: "פברואר", 3: "מרץ", 4: "אפריל", 5: "מאי", 6: "יוני",
    7: "יולי", 8: "אוגוסט", 9: "ספטמבר", 10: "אוקטובר", 11: "נובמבר", 12: "דצמבר",
}

MAJOR_HOLIDAYS = {
    "Rosh Hashana": "ראש השנה",
    "Yom Kippur": "יום כיפור",
    "Succos": "סוכות",
    "Shmini Atzeres": "שמיני עצרת / שמחת תורה",
    "Pesach": "פסח",
    "Shavuos": "שבועות",
    "Purim": "פורים",
    "Tisha B'Av": "תשעה באב",
    "Chanuka": "חנוכה",
}
EREV_ELIGIBLE = {"Rosh Hashana", "Yom Kippur", "Succos", "Pesach", "Shavuos", "Shmini Atzeres"}


def load_config(path: str | Path = "config/oncology.json") -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_zero = divmod(month_index, 12)
    return date(year, month_zero + 1, 1)


def month_dates(year: int, month: int) -> list[date]:
    return [date(year, month, day) for day in range(1, calendar.monthrange(year, month)[1] + 1)]


def hebrew_weekday(value: date) -> str:
    return HEBREW_WEEKDAYS[value.weekday()]


def _religious_holiday(value: date) -> tuple[str | None, str | None]:
    hebrew = hebrew_dates.GregorianDate(value.year, value.month, value.day).to_heb()
    english = hebrew.holiday(israel=True, hebrew=False, prefix_day=False)
    if not english:
        return None, None
    english = str(english)
    label = MAJOR_HOLIDAYS.get(english)

    # Keep the visible calendar compact, but distinguish days that operate
    # differently for staffing purposes in Israel.
    if english == "Succos":
        if hebrew.day == 15:
            label = "סוכות"
        elif 16 <= hebrew.day <= 20:
            label = "חול המועד סוכות"
        elif hebrew.day == 21:
            label = "הושענא רבה"
    elif english == "Pesach":
        if hebrew.day == 15:
            label = "פסח"
        elif 16 <= hebrew.day <= 20:
            label = "חול המועד פסח"
        elif hebrew.day == 21:
            label = "שביעי של פסח"

    return english, label


@lru_cache(maxsize=16)
def _national_holidays(year: int) -> Mapping[date, str]:
    """Return Israeli public holidays when python-holidays is available.

    The application remains usable without the optional package because religious
    holidays are calculated locally with pyluach.
    """
    try:
        import holidays  # type: ignore

        result = holidays.country_holidays("IL", years=[year], language="he")
        return {key: str(value) for key, value in result.items()}
    except Exception:
        return {}


def important_day_name(value: date, special_days: Mapping[str, str] | None = None) -> str:
    special_days = special_days or {}
    custom = special_days.get(value.isoformat(), "").strip()

    english, religious = _religious_holiday(value)
    labels: list[str] = []
    if religious:
        labels.append(religious)

    if not religious:
        national = _national_holidays(value.year).get(value)
        if national:
            labels.append(national)

    tomorrow_english, tomorrow_religious = _religious_holiday(value + timedelta(days=1))
    if tomorrow_english in EREV_ELIGIBLE and tomorrow_religious and english != tomorrow_english:
        labels.append(f"ערב {tomorrow_religious}")

    if custom:
        labels.append(custom)

    return " | ".join(dict.fromkeys(label for label in labels if label))


def build_month_table(
    year: int,
    month: int,
    special_days: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    rows = []
    for current in month_dates(year, month):
        rows.append(
            {
                "תאריך": current,
                "יום": hebrew_weekday(current),
                "חג / יום מיוחד": important_day_name(current, special_days),
            }
        )
    return pd.DataFrame(rows)


def normalize_spaces(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def build_submission(
    employee: str,
    year: int,
    month: int,
    edited_table: pd.DataFrame,
) -> dict[str, Any]:
    employee = normalize_spaces(employee)
    if not employee:
        raise ValueError("יש להזין שם עובד/ת")

    entries: list[dict[str, str]] = []
    for _, row in edited_table.iterrows():
        raw_date = row.get("תאריך")
        if isinstance(raw_date, pd.Timestamp):
            current = raw_date.date()
        elif isinstance(raw_date, datetime):
            current = raw_date.date()
        elif isinstance(raw_date, date):
            current = raw_date
        else:
            current = pd.to_datetime(raw_date, dayfirst=True).date()

        unavailable = bool(row.get("לא זמין", False))
        vacation = bool(row.get("חופש", False))
        note = normalize_spaces(row.get("הערה", ""))
        if unavailable or vacation or note:
            entries.append(
                {
                    "date": current.isoformat(),
                    "unavailable": "1" if unavailable else "0",
                    "vacation": "1" if vacation else "0",
                    "note": note,
                }
            )

    return {
        "schema": SUBMISSION_MARKER,
        "employee": employee,
        "month": f"{year:04d}-{month:02d}",
        "entries": entries,
    }


def encode_submission(payload: Mapping[str, Any]) -> str:
    return SUBMISSION_MARKER + "\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_submission(text: Any) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("התשובה ריקה")

    if SUBMISSION_MARKER in raw:
        raw = raw.split(SUBMISSION_MARKER, 1)[1].strip()

    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("לא נמצא מבנה תשובה תקין")

    payload = json.loads(raw[start : end + 1])
    if payload.get("schema") != SUBMISSION_MARKER:
        raise ValueError("גרסת התשובה אינה נתמכת")
    if not normalize_spaces(payload.get("employee")):
        raise ValueError("לא נמצא שם עובד/ת בתשובה")
    if not re.fullmatch(r"\d{4}-\d{2}", str(payload.get("month", ""))):
        raise ValueError("חודש התשובה אינו תקין")
    if not isinstance(payload.get("entries"), list):
        raise ValueError("רשימת ההעדפות אינה תקינה")
    return payload


def submissions_to_long_table(payloads: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for payload in payloads:
        employee = normalize_spaces(payload.get("employee"))
        for entry in payload.get("entries", []):
            rows.append(
                {
                    "עובד/ת": employee,
                    "תאריך": date.fromisoformat(str(entry["date"])),
                    "לא זמין": str(entry.get("unavailable", "0")) == "1",
                    "חופש": str(entry.get("vacation", "0")) == "1",
                    "הערה": normalize_spaces(entry.get("note", "")),
                }
            )
    return pd.DataFrame(rows, columns=["עובד/ת", "תאריך", "לא זמין", "חופש", "הערה"])


def availability_matrix(
    payloads: Sequence[Mapping[str, Any]],
    year: int,
    month: int,
    special_days: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    base = build_month_table(year, month, special_days)
    long_table = submissions_to_long_table(payloads)
    employees = sorted({normalize_spaces(item.get("employee")) for item in payloads if normalize_spaces(item.get("employee"))})

    result = base.copy()
    for employee in employees:
        result[employee] = ""

    if long_table.empty:
        return result

    for _, row in long_table.iterrows():
        current = row["תאריך"]
        employee = row["עובד/ת"]
        labels: list[str] = []
        if bool(row["חופש"]):
            labels.append("חופש")
        if bool(row["לא זמין"]):
            labels.append("לא זמין")
        if row["הערה"]:
            labels.append(str(row["הערה"]))
        mask = result["תאריך"] == current
        result.loc[mask, employee] = " | ".join(labels)
    return result


def availability_summary(payloads: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    long_table = submissions_to_long_table(payloads)
    employees = sorted({normalize_spaces(item.get("employee")) for item in payloads if normalize_spaces(item.get("employee"))})
    rows: list[dict[str, Any]] = []
    for employee in employees:
        employee_rows = long_table[long_table["עובד/ת"] == employee]
        rows.append(
            {
                "עובד/ת": employee,
                "ימים לא זמינים": int(employee_rows["לא זמין"].sum()) if not employee_rows.empty else 0,
                "ימי חופש": int(employee_rows["חופש"].sum()) if not employee_rows.empty else 0,
                "ימים עם הערה": int((employee_rows["הערה"] != "").sum()) if not employee_rows.empty else 0,
            }
        )
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    employee: str
    title: str
    task_code: str
    event_date: date
    all_day: bool
    start: datetime | None
    end: datetime | None
    description: str = ""


def records_to_events(records: pd.DataFrame, employee: str, config: Mapping[str, Any]) -> list[CalendarEvent]:
    if records.empty:
        return []
    employee = normalize_spaces(employee)
    defaults = config.get("event_defaults", {})
    labels = config.get("task_labels", {})
    timezone_name = str(config.get("timezone", "Asia/Jerusalem"))
    events: list[CalendarEvent] = []
    seen: set[tuple[Any, ...]] = set()

    selected = records[(records["employee"] == employee) & (records["record_type"] == "task")]
    for _, row in selected.sort_values(["date", "task_code", "source_cell"]).iterrows():
        task_code = str(row["task_code"])
        settings = defaults.get(task_code, {"all_day": True, "create": True})
        if not bool(settings.get("create", True)):
            continue
        current = row["date"]
        if isinstance(current, pd.Timestamp):
            current = current.date()
        subtype = normalize_spaces(row.get("subtype", ""))
        task_label = str(labels.get(task_code, row.get("task_label", task_code)))
        title = task_label + (f" - {subtype}" if subtype else "")
        dedupe_key = (current, employee, task_code, subtype)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        all_day = bool(settings.get("all_day", True))
        start_dt: datetime | None = None
        end_dt: datetime | None = None
        if not all_day:
            start_clock = time.fromisoformat(str(settings.get("start", "08:00")))
            end_clock = time.fromisoformat(str(settings.get("end", "16:00")))
            end_offset = int(settings.get("end_day_offset", 0))
            start_dt = datetime.combine(current, start_clock)
            end_dt = datetime.combine(current + timedelta(days=end_offset), end_clock)

        digest = sha256(f"{employee}|{current.isoformat()}|{task_code}|{subtype}".encode("utf-8")).hexdigest()[:32]
        description = f"נוצר אוטומטית ממערכת MedStaff. אזור זמן: {timezone_name}. מקור: {row.get('source_cell', '')}"
        events.append(
            CalendarEvent(
                uid=f"{digest}@medstaff-oncology",
                employee=employee,
                title=title,
                task_code=task_code,
                event_date=current,
                all_day=all_day,
                start=start_dt,
                end=end_dt,
                description=description,
            )
        )
    return events


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def events_to_ics(events: Iterable[CalendarEvent], timezone_name: str = "Asia/Jerusalem") -> bytes:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MedStaff//Oncology Scheduler//HE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-TIMEZONE:{timezone_name}",
    ]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for event in events:
        lines.extend(["BEGIN:VEVENT", f"UID:{event.uid}", f"DTSTAMP:{stamp}"])
        if event.all_day:
            lines.append(f"DTSTART;VALUE=DATE:{event.event_date.strftime('%Y%m%d')}")
            lines.append(f"DTEND;VALUE=DATE:{(event.event_date + timedelta(days=1)).strftime('%Y%m%d')}")
        else:
            assert event.start is not None and event.end is not None
            lines.append(f"DTSTART;TZID={timezone_name}:{event.start.strftime('%Y%m%dT%H%M%S')}")
            lines.append(f"DTEND;TZID={timezone_name}:{event.end.strftime('%Y%m%dT%H%M%S')}")
        lines.append(f"SUMMARY:{_ics_escape(event.title)}")
        lines.append(f"DESCRIPTION:{_ics_escape(event.description)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")
