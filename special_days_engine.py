"""Unified special-day engine for planning context across MedStaff tools.

Data sources:
1. Google public holiday calendars (live, best effort).
2. Deterministic annual/Hebrew-date rules for selected awareness and family days.
3. Configurable per-date overrides for exceptional operational changes.

The engine deliberately separates source data from the whitelist/filter rules.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from functools import lru_cache
from typing import Mapping
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd
from pyluach import dates as hebrew_dates

import core


GOOGLE_CALENDAR_IDS = (
    "en.jewish#holiday@group.v.calendar.google.com",  # Israel holidays/observances
    "en.judaism#holiday@group.v.calendar.google.com",
    "en.islamic#holiday@group.v.calendar.google.com",
    "en.christian#holiday@group.v.calendar.google.com",
    "en.orthodox_christianity#holiday@group.v.calendar.google.com",
)

# Rules define what is relevant. Dates are taken from Google whenever possible.
# Matching is intentionally broad enough to tolerate small wording changes.
GOOGLE_WHITELIST: tuple[tuple[tuple[str, ...], str], ...] = (
    (("rosh hashana", "rosh hashanah"), "ראש השנה"),
    (("fast of gedalia", "tzom gedalia"), "צום גדליה"),
    (("yom kippur",), "יום כיפור"),
    (("sukkot", "succot", "succos"), "סוכות"),
    (("hoshana rabba", "hoshanah rabbah"), "הושענא רבה"),
    (("shemini atzeret", "shmini atzeres"), "שמיני עצרת / שמחת תורה"),
    (("simchat torah",), "שמיני עצרת / שמחת תורה"),
    (("hanukkah", "chanukah", "chanuka"), "חנוכה"),
    (("tenth of tevet", "asarah b'tevet", "10th of tevet"), "עשרה בטבת"),
    (("tu bishvat", "tu b'shvat", "15 shvat"), "ט\"ו בשבט"),
    (("fast of esther", "ta'anit esther"), "תענית אסתר"),
    (("purim",), "פורים"),
    (("passover", "pesach"), "פסח"),
    (("lag baomer", "lag b'omer"), "ל\"ג בעומר"),
    (("shavuot", "shavuos"), "שבועות"),
    (("seventeenth of tammuz", "17th of tammuz", "tzom tammuz"), "י\"ז בתמוז"),
    (("tisha b'av", "tisha bav"), "תשעה באב"),
    (("holocaust remembrance", "yom hashoah"), "יום הזיכרון לשואה ולגבורה"),
    (("memorial day", "yom hazikaron"), "יום הזיכרון לחללי מערכות ישראל ונפגעי פעולות האיבה"),
    (("independence day", "yom haatzmaut", "yom ha'atzmaut"), "יום העצמאות"),
    (("election day", "knesset election"), "יום הבחירות לכנסת"),
    (("sigd",), "סיגד"),
    (("ramadan start", "first day of ramadan", "ramadan begins"), "תחילת רמדאן"),
    (("eve of eid al-fitr", "eid al-fitr eve", "eve of eid ul-fitr"), "ערב עיד אל-פיטר"),
    (("eid al-fitr", "eid ul-fitr"), "עיד אל-פיטר"),
    (("eve of eid al-adha", "eid al-adha eve", "eve of eid ul-adha"), "ערב עיד אל-אדחא / חג הקורבן"),
    (("eid al-adha", "eid ul-adha"), "עיד אל-אדחא / חג הקורבן"),
    (("islamic new year", "muharram"), "ראש השנה ההיג'רית"),
    (("prophet's birthday", "mawlid", "milad un nabi"), "יום הולדת הנביא מוחמד"),
    (("armenian christmas",), "חג המולד - ארמני"),
    (("orthodox christmas",), "חג המולד - אורתודוקסי"),
    (("christmas eve",), "ערב חג המולד"),
    (("christmas day", "christmas"), "חג המולד"),
    (("orthodox good friday",), "יום שישי הטוב - אורתודוקסי"),
    (("good friday",), "יום שישי הטוב"),
    (("orthodox easter",), "פסחא - אורתודוקסי"),
    (("easter",), "פסחא"),
    (("annunciation",), "חג הבשורה"),
    (("nabi shu", "prophet shu", "shuaib", "shu'ayb"), "חג הנביא שועייב"),
    (("nabi sabalan", "prophet sabalan", "sabalan"), "חג הנביא סבלאן"),
)

# Fixed-date awareness days. These are policy/rule data, not inferred holidays.
AWARENESS_DAYS: Mapping[tuple[int, int], str] = {
    (2, 4): "יום הסרטן הבינלאומי",
    (2, 15): "יום הסרטן הבינלאומי בילדים",
    (3, 8): "יום האישה הבינלאומי",
    (5, 8): "יום המודעות הבינלאומי לסרטן השחלה",
    (5, 28): "יום המודעות הבינלאומי לסרטן הדם",
    (5, 31): "היום הבינלאומי ללא עישון",
    (8, 1): "יום סרטן הריאה העולמי",
    (9, 20): "יום האונקולוגיה הגינקולוגית העולמי",
    (9, 24): "יום חקר הסרטן העולמי",
    (10, 13): "יום המודעות לסרטן שד גרורתי",
}


def _unfold_ics(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape_ics(value: str) -> str:
    return (
        value.replace("\\n", " ")
        .replace("\\N", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def _parse_google_ics(text: str, year: int) -> list[tuple[date, str]]:
    events: list[tuple[date, str]] = []
    current_date: date | None = None
    summary = ""
    in_event = False
    for line in _unfold_ics(text):
        if line == "BEGIN:VEVENT":
            in_event = True
            current_date = None
            summary = ""
            continue
        if line == "END:VEVENT":
            if in_event and current_date and current_date.year == year and summary:
                events.append((current_date, summary))
            in_event = False
            continue
        if not in_event:
            continue
        if line.startswith("DTSTART") and ":" in line:
            raw = line.split(":", 1)[1].strip()
            match = re.match(r"(\d{4})(\d{2})(\d{2})", raw)
            if match:
                try:
                    current_date = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                except ValueError:
                    current_date = None
        elif line.startswith("SUMMARY") and ":" in line:
            summary = _unescape_ics(line.split(":", 1)[1])
    return events


def _google_url(calendar_id: str) -> str:
    return f"https://calendar.google.com/calendar/ical/{quote(calendar_id, safe='')}/public/basic.ics"


@lru_cache(maxsize=64)
def _google_events(calendar_id: str, year: int) -> tuple[tuple[date, str], ...]:
    """Fetch one public Google holiday calendar. Failure is non-fatal."""
    try:
        request = Request(_google_url(calendar_id), headers={"User-Agent": "MedStaff/1.0"})
        with urlopen(request, timeout=3) as response:  # nosec - fixed Google host
            payload = response.read().decode("utf-8", errors="replace")
        return tuple(_parse_google_ics(payload, year))
    except Exception:
        return ()


def _match_google_summary(summary: str) -> str:
    folded = re.sub(r"\s+", " ", summary).strip().casefold()
    for aliases, label in GOOGLE_WHITELIST:
        if any(alias in folded for alias in aliases):
            return label
    return ""


@lru_cache(maxsize=16)
def _google_special_days(year: int) -> Mapping[date, tuple[str, ...]]:
    result: dict[date, list[str]] = {}
    for calendar_id in GOOGLE_CALENDAR_IDS:
        for event_date, summary in _google_events(calendar_id, year):
            label = _match_google_summary(summary)
            if label:
                result.setdefault(event_date, []).append(label)
    return {key: tuple(dict.fromkeys(values)) for key, values in result.items()}


def _hebrew_date_in_gregorian_year(year: int, month: int, day: int) -> date | None:
    """Return the requested Hebrew date that falls in a Gregorian year."""
    for hyear in range(year + 3759, year + 3762):
        try:
            greg = hebrew_dates.HebrewDate(hyear, month, day).to_greg()
            candidate = date(greg.year, greg.month, greg.day)
            if candidate.year == year:
                return candidate
        except Exception:
            continue
    return None


def _family_day(year: int) -> date | None:
    # Israel Family Day is 30 Shevat. pyluach month 11 is Shevat.
    return _hebrew_date_in_gregorian_year(year, 11, 30)


def _school_start(year: int, base_labels: Mapping[date, list[str]]) -> date:
    """Default Ministry of Education rule with operational-calendar adjustment.

    The authoritative date can always be replaced through special_days_overrides.
    This fallback moves Sep 1 forward when it is Saturday or an identified full holiday.
    """
    current = date(year, 9, 1)
    full_holiday_terms = (
        "ראש השנה",
        "יום כיפור",
        "סוכות",
        "שמיני עצרת",
        "פסח",
        "שביעי של פסח",
        "שבועות",
    )
    while current.weekday() == 5 or any(
        any(term in label for term in full_holiday_terms) for label in base_labels.get(current, [])
    ):
        current += timedelta(days=1)
    return current


def _add_label(target: dict[date, list[str]], when: date | None, label: str) -> None:
    if when is None:
        return
    target.setdefault(when, [])
    if label not in target[when]:
        target[when].append(label)


def _local_fallback_labels(year: int) -> dict[date, list[str]]:
    """Retain robust local Jewish/public holiday calculation if Google is unavailable."""
    result: dict[date, list[str]] = {}
    for month in range(1, 13):
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            current = date(year, month, day)
            label = core.important_day_name(current)
            if label:
                for part in [item.strip() for item in label.split("|") if item.strip()]:
                    _add_label(result, current, part)
    return result


@lru_cache(maxsize=16)
def _merge_source_days(year: int) -> Mapping[date, tuple[str, ...]]:
    result = _local_fallback_labels(year)
    for when, labels in _google_special_days(year).items():
        for label in labels:
            # Local calculation gives more precise labels for Hol Hamoed / final festival days.
            existing = result.get(when, [])
            if label == "סוכות" and any("חול המועד סוכות" in item or "הושענא רבה" in item for item in existing):
                continue
            if label == "פסח" and any("חול המועד פסח" in item or "שביעי של פסח" in item for item in existing):
                continue
            _add_label(result, when, label)

    # Family/social/medical awareness rules requested for the planning context.
    _add_label(result, _family_day(year), "יום המשפחה")
    for (month, day), label in AWARENESS_DAYS.items():
        try:
            _add_label(result, date(year, month, day), label)
        except ValueError:
            pass

    # School-year milestones. Actual exceptional dates can override these in config.
    start = _school_start(year, result)
    _add_label(result, start, "תחילת שנת הלימודים")
    _add_label(result, date(year, 6, 20), "סיום שנת הלימודים - על יסודי")
    _add_label(result, date(year, 6, 30), "סיום שנת הלימודים - גנים ויסודי")
    return {key: tuple(values) for key, values in result.items()}


def _config_overrides(config: Mapping | None) -> Mapping[str, str]:
    if not config:
        return {}
    raw = config.get("special_days_overrides", config.get("special_days", {}))
    return raw if isinstance(raw, Mapping) else {}


def special_day_name(value: date, config: Mapping | None = None) -> str:
    labels = list(_merge_source_days(value.year).get(value, ()))
    override = str(_config_overrides(config).get(value.isoformat(), "") or "").strip()
    if override:
        # A single '-' suppresses generated labels for an exceptional date.
        if override == "-":
            labels = []
        else:
            labels.append(override)
    return " | ".join(dict.fromkeys(label for label in labels if label))


def build_month_table(year: int, month: int, config: Mapping | None = None) -> pd.DataFrame:
    rows = []
    for current in core.month_dates(year, month):
        rows.append(
            {
                "תאריך": current,
                "יום": core.hebrew_weekday(current),
                "חג / יום מיוחד": special_day_name(current, config),
            }
        )
    return pd.DataFrame(rows)


def install(app_module) -> None:
    """Install the same special-day engine into Tools 1, 2 and schedule parsing."""
    if getattr(app_module, "_special_days_engine_installed", False):
        return

    import schedule_parser

    def app_build_month_table(year: int, month: int, special_days=None):
        # Keep compatibility with legacy callers while using the central CONFIG.
        config = dict(getattr(app_module, "CONFIG", {}) or {})
        if special_days:
            merged = dict(_config_overrides(config))
            merged.update(dict(special_days))
            config["special_days_overrides"] = merged
        return build_month_table(year, month, config)

    def app_important_day_name(value: date, special_days=None):
        config = dict(getattr(app_module, "CONFIG", {}) or {})
        if special_days:
            merged = dict(_config_overrides(config))
            merged.update(dict(special_days))
            config["special_days_overrides"] = merged
        return special_day_name(value, config)

    app_module.build_month_table = app_build_month_table
    app_module.important_day_name = app_important_day_name
    schedule_parser.important_day_name = app_important_day_name
    app_module._special_days_engine_installed = True
