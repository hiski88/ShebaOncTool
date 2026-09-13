"""Initial shell for Tool 6 - worker administration."""
from __future__ import annotations


def render(app_module) -> None:
    st = app_module.st
    app_module.render_header(
        "6. ניהול עובדים",
        "ניהול מצבת עובדים, פרטים תעסוקתיים ותקופות התמחות.",
    )

    action = st.radio(
        "בחירת פעולה",
        [
            "הוספת עובד/ת",
            "עריכת עובד/ת",
            "צפייה ברשימת עובדים",
            "ניהול התמחות ותקופות",
        ],
        key="tool6_action",
    )

    st.divider()
    st.info(f"המסך '{action}' ייבנה בשלב הבא.")
