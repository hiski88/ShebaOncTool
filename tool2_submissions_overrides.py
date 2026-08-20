"""Tool 2: read monthly preference submissions directly from Google Sheets."""
from __future__ import annotations

from collections import Counter

import pandas as pd

from google_sheets_submissions import configured, read_submissions


def install(app_module) -> None:
    if getattr(app_module, "_tool2_submissions_override_installed", False):
        return

    def tool_manager_from_sheets() -> None:
        st = app_module.st
        app_module.render_header(
            "2. ריכוז העדפות ובניית לוז",
            "בחירת חודש מציגה אוטומטית את כל ההגשות שנקלטו מהצוות.",
        )
        year, month = app_module.month_selector("manager", offset=1)

        if not configured(st):
            st.error("חיבור Google Sheets אינו מוגדר באפליקציה.")
            return

        try:
            submissions = read_submissions(st, year, month)
        except Exception as exc:
            st.error(f"לא ניתן לקרוא את ההגשות מ-Google Sheets: {exc}")
            return

        month_display = f"{month:02d}-{year:04d}"
        if not submissions:
            st.info(f"לא נמצאו הגשות לחודש {month_display}.")
            return

        counts = Counter(item["שם עובד"] for item in submissions)
        unique_employees = len(counts)
        duplicate_names = [name for name, count in counts.items() if count > 1]

        st.success(
            f"נמצאו {len(submissions)} הגשות של {unique_employees} עובדים לחודש {month_display}."
        )

        if duplicate_names:
            details = ", ".join(f"{name} ({counts[name]})" for name in duplicate_names)
            st.warning(f"זוהו הגשות כפולות: {details}")

        display_rows = []
        seen = Counter()
        for item in submissions:
            name = item["שם עובד"]
            seen[name] += 1
            count = counts[name]
            is_newest_for_name = seen[name] == 1
            duplicate_status = ""
            if count > 1:
                duplicate_status = f"{seen[name]} מתוך {count}"
                if is_newest_for_name:
                    duplicate_status += " - החדשה ביותר"

            # Streamlit's grid lays physical columns left-to-right even inside
            # the RTL app. Store them in reverse physical order so the visual
            # reading order from the right starts with the manual include flag.
            display_rows.append(
                {
                    "כפילות": duplicate_status,
                    "הערות": item["הערות"],
                    "חופשים": item["חופשים"],
                    "חסימות": item["חסימות"],
                    "שם עובד": name,
                    "זמן הגשה": item["זמן הגשה"],
                    "לכלול בתכנון": is_newest_for_name,
                }
            )

        st.subheader("בחירת הגשות לתכנון")
        selected_table = st.data_editor(
            pd.DataFrame(display_rows),
            width="stretch",
            hide_index=True,
            disabled=["זמן הגשה", "שם עובד", "חסימות", "חופשים", "הערות", "כפילות"],
            column_config={
                "לכלול בתכנון": st.column_config.CheckboxColumn("לכלול בתכנון"),
            },
            key=f"manager_submission_selection_{year}_{month}",
        )

        selected_count = int(selected_table["לכלול בתכנון"].fillna(False).astype(bool).sum())
        st.caption(
            f"נבחרו {selected_count} מתוך {len(submissions)} הגשות. "
            "בכפילות עם שם זהה מסומנת אוטומטית רק ההגשה החדשה ביותר, וניתן לשנות ידנית."
        )

    app_module.tool_manager = tool_manager_from_sheets
    app_module._tool2_submissions_override_installed = True
