"""Streamlit entry point for the oncology scheduling prototype."""
from radiation_overrides import install

install()

from app_v2 import main

main()
