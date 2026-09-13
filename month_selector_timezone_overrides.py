"""Timezone-safe month selector shared by planning tools."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def install(app_module) -> None:
    if getattr(app_module, "_timezone_month_selector_installed", False):
        return

    def month_selector(key: str, offset: int = 1) -> tuple[int, int]:
        st = app_module.st
        timezone_name = str(app_module.CONFIG.get("timezone", "Asia/Jerusalem") or "Asia/Jerusalem")
        try:
            today = datetime.now(ZoneInfo(timezone_name)).date()
        except Exception:
            today = datetime.now(ZoneInfo("Asia/Jerusalem")).date()

        default = app_module.add_months(today.replace(day=1), offset)
        years = list(range(today.year - 1, today.year + 5))
        if default.year not in years:
            years.append(default.year)
            years.sort()

        col_year, col_month = st.columns([1, 1])
        with col_year:
            year = st.selectbox(
                "שנה",
                years,
                index=years.index(default.year),
                key=f"{key}_year",
            )
        with col_month:
            month = st.selectbox(
                "חודש",
                list(range(1, 13)),
                index=default.month - 1,
                format_func=lambda number: app_module.HEBREW_MONTHS[number],
                key=f"{key}_month",
            )
        return int(year), int(month)

    app_module.month_selector = month_selector
    app_module._timezone_month_selector_installed = True
