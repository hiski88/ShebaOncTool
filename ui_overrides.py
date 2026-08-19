"""UI and calendar presentation overrides for the Streamlit app."""
from __future__ import annotations

import streamlit as st


CALENDAR_EXCLUDED_CODES = {
    "after_duty",
    "absence",
    "absence_other",
}


def install(app_module) -> None:
    """Apply RTL layout fixes and suppress redundant post-duty absences."""
    # Calendar candidates are intentionally conservative: generic absence and
    # post-duty status are operational consequences, not useful calendar events.
    for code in CALENDAR_EXCLUDED_CODES:
        app_module.CALENDAR_TASK_CODES.discard(code)

    st.markdown(
        """
        <style>
        html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            direction: rtl !important;
            text-align: right !important;
        }

        [data-testid="stMainBlockContainer"],
        .main .block-container,
        [data-testid="stMarkdownContainer"],
        [data-testid="stWidgetLabel"],
        [data-testid="stCaptionContainer"],
        label, p, h1, h2, h3, h4, h5, h6 {
            direction: rtl !important;
            text-align: right !important;
        }

        input, textarea,
        div[data-baseweb="select"],
        div[data-baseweb="select"] *,
        [data-testid="stTextInput"] *,
        [data-testid="stTextArea"] *,
        [data-testid="stRadio"] *,
        [data-testid="stMultiSelect"] * {
            direction: rtl !important;
            text-align: right !important;
        }

        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] * {
            direction: rtl !important;
            text-align: right !important;
        }

        section[data-testid="stSidebar"] [role="radiogroup"] label,
        section[data-testid="stSidebar"] [role="radiogroup"] label > div {
            direction: rtl !important;
            text-align: right !important;
            justify-content: flex-start !important;
        }

        @media (min-width: 769px) {
            section[data-testid="stSidebar"] {
                position: fixed !important;
                top: 0 !important;
                right: 0 !important;
                left: auto !important;
                height: 100vh !important;
                z-index: 999 !important;
                border-left: 1px solid rgba(49, 51, 63, 0.12) !important;
                border-right: 0 !important;
            }

            [data-testid="stAppViewContainer"] > .main,
            [data-testid="stMain"] {
                margin-left: 0 !important;
                margin-right: 21rem !important;
            }

            header[data-testid="stHeader"] {
                left: 0 !important;
                right: 21rem !important;
            }
        }

        div[data-testid="stDataFrame"],
        div[data-testid="stDataEditor"],
        div[data-testid="stDataFrame"] [role="grid"],
        div[data-testid="stDataEditor"] [role="grid"] {
            direction: rtl !important;
        }

        div[data-testid="stDataFrame"] [role="columnheader"],
        div[data-testid="stDataFrame"] [role="gridcell"],
        div[data-testid="stDataEditor"] [role="columnheader"],
        div[data-testid="stDataEditor"] [role="gridcell"] {
            direction: rtl !important;
            text-align: right !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
