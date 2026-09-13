"""UI and calendar presentation overrides for the Streamlit app."""
from __future__ import annotations

import streamlit as st


CALENDAR_EXCLUDED_CODES = {
    "after_duty",
    "absence",
    "absence_other",
}


def install(app_module) -> None:
    """Apply RTL layout fixes and calendar filtering rules."""
    for code in CALENDAR_EXCLUDED_CODES:
        app_module.CALENDAR_TASK_CODES.discard(code)

    app_module.CALENDAR_TASK_CODES.add("rest_entitlement")
    aliases = app_module.CONFIG.setdefault("activity_aliases", [])
    if not any(item.get("code") == "rest_entitlement" for item in aliases):
        aliases.insert(
            0,
            {
                "terms": ["ת\"ש", "ת״ש", "ת'ש", "תש"],
                "code": "rest_entitlement",
                "label": "ת\"ש - יום מנוחה",
                "kind": "status",
            },
        )
    non_names = app_module.CONFIG.setdefault("non_name_terms", [])
    for term in ["ת\"ש", "ת״ש", "ת'ש", "תש"]:
        if term not in non_names:
            non_names.append(term)
    app_module.CONFIG.setdefault("task_labels", {})["rest_entitlement"] = "ת\"ש - יום מנוחה"
    app_module.CONFIG.setdefault("event_defaults", {})["rest_entitlement"] = {
        "all_day": True,
        "create": True,
    }

    st.markdown(
        """
        <style>
        html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
            direction: rtl !important;
            text-align: right !important;
        }

        [data-testid="stMainBlockContainer"],
        .main .block-container {
            direction: rtl !important;
            text-align: right !important;
            max-width: none !important;
            width: 100% !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }

        [data-testid="stMarkdownContainer"],
        [data-testid="stWidgetLabel"],
        [data-testid="stCaptionContainer"],
        [data-testid="stColumn"],
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

        [role="listbox"],
        [role="listbox"] *,
        [role="option"],
        [role="option"] *,
        div[data-baseweb="popover"],
        div[data-baseweb="popover"] * {
            direction: rtl !important;
            text-align: right !important;
        }

        [role="option"] {
            justify-content: flex-start !important;
        }

        [role="option"] > div,
        [role="option"] span,
        [role="listbox"] li {
            width: 100% !important;
            text-align: right !important;
        }

        [data-testid="stTimeInput"],
        [data-testid="stTimeInput"] > div,
        [data-testid="stTimeInput"] label,
        [data-testid="stTimeInput"] [data-testid="stWidgetLabel"] {
            direction: rtl !important;
            text-align: right !important;
        }

        input[type="time"],
        [data-testid="stTimeInput"] input,
        [data-testid="stTimeInput"] input[type="time"] {
            direction: ltr !important;
            text-align: right !important;
            unicode-bidi: isolate !important;
        }

        input[type="time"]::-webkit-datetime-edit,
        input[type="time"]::-webkit-datetime-edit-fields-wrapper,
        input[type="time"]::-webkit-datetime-edit-hour-field,
        input[type="time"]::-webkit-datetime-edit-minute-field,
        input[type="time"]::-webkit-datetime-edit-second-field,
        input[type="time"]::-webkit-datetime-edit-ampm-field,
        input[type="time"]::-webkit-datetime-edit-text {
            direction: ltr !important;
            unicode-bidi: isolate !important;
            text-align: right !important;
        }

        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] * {
            direction: rtl !important;
            text-align: right !important;
        }

        section[data-testid="stSidebar"] [data-testid="stRadio"] > label,
        section[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stWidgetLabel"] {
            display: none !important;
        }

        section[data-testid="stSidebar"] [role="radiogroup"] label,
        section[data-testid="stSidebar"] [role="radiogroup"] label > div {
            direction: rtl !important;
            text-align: right !important;
            justify-content: flex-start !important;
        }

        /* Do not override sidebar position, width, transform or z-index.
           Streamlit owns the open/collapse animation and main-content resize. */
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"],
        section[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarUserContent"] {
            overflow: hidden !important;
        }

        div[data-testid="stDataFrame"],
        div[data-testid="stDataEditor"] {
            direction: rtl !important;
            width: 100% !important;
            max-width: none !important;
        }

        div[data-testid="stDataFrame"] > div,
        div[data-testid="stDataEditor"] > div,
        div[data-testid="stDataFrame"] [role="grid"],
        div[data-testid="stDataEditor"] [role="grid"] {
            direction: rtl !important;
            width: 100% !important;
            max-width: none !important;
        }

        div[data-testid="stDataFrame"] [role="columnheader"],
        div[data-testid="stDataFrame"] [role="gridcell"],
        div[data-testid="stDataEditor"] [role="columnheader"],
        div[data-testid="stDataEditor"] [role="gridcell"] {
            direction: rtl !important;
            text-align: right !important;
        }

        @media (max-width: 768px) {
            [data-testid="stMainBlockContainer"], .main .block-container {
                padding-left: .75rem !important;
                padding-right: .75rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
