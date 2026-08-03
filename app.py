"""Streamlit entry point for the oncology scheduling prototype."""
from __future__ import annotations

from pathlib import Path

from radiation_overrides import install

install()

legacy_path = Path(__file__).with_name("app_legacy.py")
legacy_globals = {
    "__name__": "__main__",
    "__file__": str(legacy_path),
    "__package__": None,
}
exec(compile(legacy_path.read_text(encoding="utf-8"), str(legacy_path), "exec"), legacy_globals)
