"""Configurable worker-profile rules shared by registration and manager workflows."""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from core import load_config


DEFAULT_MINIMUM_AGE = 20
DEFAULT_BIRTH_DATE_AGE = 30
DEFAULT_PICKER_YEARS_BACK = 80


@lru_cache(maxsize=1)
def _profile_config() -> dict[str, object]:
    config = load_config()
    raw = config.get("worker_profile", {})
    return raw if isinstance(raw, dict) else {}


def _positive_int(value: object, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def worker_age_settings() -> tuple[int, int, int]:
    """Return minimum age, default displayed age and picker lookback years."""
    raw = _profile_config()
    minimum_age = _positive_int(raw.get("minimum_age"), DEFAULT_MINIMUM_AGE)
    default_age = _positive_int(raw.get("birth_date_default_age"), DEFAULT_BIRTH_DATE_AGE)
    picker_years_back = _positive_int(
        raw.get("birth_date_picker_years_back"), DEFAULT_PICKER_YEARS_BACK
    )

    default_age = max(default_age, minimum_age)
    picker_years_back = max(picker_years_back, default_age)
    return minimum_age, default_age, picker_years_back


def local_today() -> date:
    config = load_config()
    timezone = str(config.get("timezone", "Asia/Jerusalem") or "Asia/Jerusalem")
    return datetime.now(ZoneInfo(timezone)).date()


def years_ago(reference: date, years: int) -> date:
    """Return the same month/day N years earlier, handling 29 February safely."""
    target_year = reference.year - years
    try:
        return reference.replace(year=target_year)
    except ValueError:
        return reference.replace(year=target_year, month=2, day=28)


def birth_date_input_values(reference: date | None = None) -> tuple[date, date, date]:
    """Return (default, earliest, latest) values for a birth-date picker."""
    today = reference or local_today()
    minimum_age, default_age, picker_years_back = worker_age_settings()
    default_value = years_ago(today, default_age)
    earliest_value = years_ago(today, picker_years_back)
    latest_value = years_ago(today, minimum_age)
    return default_value, earliest_value, latest_value


def validate_worker_birth_date(birth_date: date | None, reference: date | None = None) -> str | None:
    """Validate the configurable minimum worker age."""
    if birth_date is None:
        return None
    today = reference or local_today()
    minimum_age, _, _ = worker_age_settings()
    latest_allowed = years_ago(today, minimum_age)
    if birth_date > latest_allowed:
        return f"גיל העובד/ת חייב להיות לפחות {minimum_age}."
    return None
