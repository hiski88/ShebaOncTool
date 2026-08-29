"""Keep Tool 1 output synchronized and render its reviewed final actions in one place."""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
from contextlib import nullcontext

import streamlit.components.v1 as components

from google_sheets_submissions import configured, submit_preferences


VISIBLE_OUTPUT_LABEL = "טקסט להעתקה"
HIDDEN_OUTPUT_LABEL = "קוד לקליטה אוטומטית"
HIDDEN_EXPANDER_LABEL = "קוד מערכת למתכנן - מתקדם"
HIDDEN_CAPTIONS = {
    "זה הפלט שנוח להעתיק ולשלוח, בדומה לכלי של פנימית ד'.",
    "אין צורך לקרוא או לערוך את הקוד. הוא מיועד לקליטה אוטומטית בכלי הריכוז.",
}
HIDDEN_WARNINGS = {
    "יש תאריכים שסומנו גם כחופש וגם כחסימה. המערכת תשמור את שני הסימונים.",
}
_MONTH_FROM_FILENAME = re.compile(r"_(\d{4})_(\d{2})\.xlsx$")
CONTROL_ROW_LABEL = "כל החודש"

# Shared visual language for employee availability/preferences.
COLOR_VACATION = "#ff8a8a"
COLOR_HALF_BLOCK = "#ffbf69"
COLOR_FULL_BLOCK = "#ffe66d"
COLOR_WANTS_DUTY = "#8bd17c"
COLOR_AVAILABLE = "#ffffff"


def _render_copy_button(value: str) -> None:
    if not value:
        return

    value_json = json.dumps(value, ensure_ascii=False)
    button_label = html.escape("העתקה")
    components.html(
        f"""
        <div dir="rtl" style="font-family: sans-serif; margin-top: -4px; margin-bottom: 8px;">
          <button id="copy-btn" style="
              width: 100%;
              min-height: 42px;
              border: 1px solid rgba(49, 51, 63, 0.22);
              border-radius: 8px;
              background: white;
              cursor: pointer;
              font-size: 14px;
              font-weight: 600;
          ">{button_label}</button>
        </div>
        <script>
          const textToCopy = {value_json};
          const button = document.getElementById('copy-btn');
          button.addEventListener('click', async () => {{
            let copied = false;
            try {{
              await navigator.clipboard.writeText(textToCopy);
              copied = true;
            }} catch (err) {{
              try {{
                const area = document.createElement('textarea');
                area.value = textToCopy;
                area.style.position = 'fixed';
                area.style.opacity = '0';
                document.body.appendChild(area);
                area.focus();
                area.select();
                copied = document.execCommand('copy');
                document.body.removeChild(area);
              }} catch (fallbackErr) {{}}
            }}
            if (copied) {{
              button.textContent = {json.dumps("הועתק", ensure_ascii=False)};
              setTimeout(() => {{ button.textContent = {json.dumps("העתקה", ensure_ascii=False)}; }}, 1400);
            }}
          }});
        </script>
        """,
        height=58,
    )


def _real_rows(edited):
    try:
        if "יום" in edited.columns:
            return edited[edited["יום"].astype(str) != CONTROL_ROW_LABEL].copy()
    except Exception:
        pass
    return edited.copy()


def _day_list(edited, column: str) -> list[str]:
    result: list[str] = []
    if column not in edited.columns:
        return result
    for _, row in _real_rows(edited).iterrows():
        if not bool(row.get(column, False)):
            continue
        date_value = row.get("תאריך")
        try:
            result.append(str(int(date_value.day)))
        except Exception:
            continue
    return result


def _submission_signature(employee: str, year: int, month: int, edited, general_note: str) -> str:
    rows = []
    for _, row in _real_rows(edited).iterrows():
        date_value = row.get("תאריך")
        try:
            date_text = date_value.strftime("%Y-%m-%d")
        except Exception:
            date_text = str(date_value or "")
        rows.append(
            {
                "date": date_text,
                "vacation": bool(row.get("חופש", False)),
                "full": bool(row.get("חסימת תורנות מלאה", row.get("חסימה", False))),
                "half": bool(row.get("חסימת תורנות חצי", False)),
                "wants": bool(row.get("מעוניין בתורנות", False)),
            }
        )
    payload = {
        "employee": employee.strip(),
        "year": int(year),
        "month": int(month),
        "general_note": str(general_note or "").strip(),
        "rows": rows,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _status_for_row(row) -> tuple[str, str, str]:
    # Priority reflects actual availability: vacation > half block > full block > positive preference.
    if bool(row.get("חופש", False)):
        return "XX", COLOR_VACATION, "חופש - לא זמין לתורנות חצי או מלאה"
    if bool(row.get("חסימת תורנות חצי", False)):
        return "½X", COLOR_HALF_BLOCK, "חסימת תורנות חצי - חוסמת גם תורנות מלאה"
    if bool(row.get("חסימת תורנות מלאה", row.get("חסימה", False))):
        return "X", COLOR_FULL_BLOCK, "חסימת תורנות מלאה בלבד"
    if bool(row.get("מעוניין בתורנות", False)):
        return "V", COLOR_WANTS_DUTY, "מעוניין בתורנות"
    return "", COLOR_AVAILABLE, ""


def _legend_html() -> str:
    return f"""
    <div dir="rtl" style="margin:0.25rem 0 0.8rem 0;line-height:2.2;">
      <b>מקרא:</b>
      <span style="background:{COLOR_VACATION};border:1px solid #d95f5f;padding:4px 9px;border-radius:5px;margin:0 4px;"><b>XX</b> חופש</span>
      <span style="background:{COLOR_HALF_BLOCK};border:1px solid #d9943e;padding:4px 9px;border-radius:5px;margin:0 4px;"><b>½X</b> חסימת חצי וגם מלאה</span>
      <span style="background:{COLOR_FULL_BLOCK};border:1px solid #d5bd38;padding:4px 9px;border-radius:5px;margin:0 4px;"><b>X</b> חסימת מלאה בלבד</span>
      <span style="background:{COLOR_WANTS_DUTY};border:1px solid #58a64a;padding:4px 9px;border-radius:5px;margin:0 4px;"><b>V</b> מעוניין בתורנות</span>
      <span style="background:#ffffff;border:1px solid #bdbdbd;padding:4px 9px;border-radius:5px;margin:0 4px;">ריק - לא דווחה מגבלה או העדפה</span>
    </div>
    """


def _render_preview(st, employee: str, edited, general_note: str) -> None:
    st.subheader("תצוגה לפני אישור")
    st.markdown(_legend_html(), unsafe_allow_html=True)

    header_cells = ["תאריך", "יום", "חג / יום מיוחד", employee]
    html_rows = [
        "<tr>"
        + "".join(
            f'<th style="border:1px solid #cfcfcf;background:#dbe4f0;padding:7px;text-align:center;font-weight:700;">{html.escape(str(value))}</th>'
            for value in header_cells
        )
        + "</tr>"
    ]

    for _, row in _real_rows(edited).iterrows():
        date_value = row.get("תאריך")
        try:
            date_text = date_value.strftime("%d.%m.%Y")
        except Exception:
            date_text = str(date_value or "")
        day_text = str(row.get("יום", "") or "")
        holiday_text = str(row.get("חג / יום מיוחד", "") or "")
        symbol, background, description = _status_for_row(row)
        title_attr = f' title="{html.escape(description)}"' if description else ""
        html_rows.append(
            "<tr>"
            f'<td style="border:1px solid #dddddd;padding:6px;text-align:center;white-space:nowrap;">{html.escape(date_text)}</td>'
            f'<td style="border:1px solid #dddddd;padding:6px;text-align:center;">{html.escape(day_text)}</td>'
            f'<td style="border:1px solid #dddddd;padding:6px;text-align:center;">{html.escape(holiday_text)}</td>'
            f'<td{title_attr} style="border:1px solid #c9c9c9;padding:6px;text-align:center;background:{background};font-weight:800;">{html.escape(symbol)}</td>'
            "</tr>"
        )

    st.markdown(
        '<div dir="rtl" style="overflow-x:auto;">'
        '<table style="width:100%;border-collapse:collapse;font-size:0.94rem;">'
        + "".join(html_rows)
        + "</table></div>",
        unsafe_allow_html=True,
    )

    note = str(general_note or "").strip()
    if note:
        st.markdown(f"**הערה כללית שתישלח למתכנן:** {html.escape(note)}")
    else:
        st.caption("הערה כללית: לא הוזנה הערה.")

    st.info("זהו המידע שיועבר למתכנן. אירועי היומן וההערות האישיות אינם נשלחים.")


def _build_csv(employee: str, year: int, month: int, edited, general_note: str) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "שם עובד",
            "חודש",
            "חסימת תורנות מלאה",
            "חסימת תורנות חצי",
            "חופשים",
            "מעוניין בתורנות",
            "הערה כללית",
        ]
    )
    writer.writerow(
        [
            employee.strip(),
            f"{year:04d}-{month:02d}",
            ",".join(_day_list(edited, "חסימת תורנות מלאה")),
            ",".join(_day_list(edited, "חסימת תורנות חצי")),
            ",".join(_day_list(edited, "חופש")),
            ",".join(_day_list(edited, "מעוניין בתורנות")),
            str(general_note or "").strip(),
        ]
    )
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def install(app_module) -> None:
    """Render copy, reviewed preview, submit, and CSV download in that order."""
    if getattr(app_module, "_preferences_output_override_installed", False):
        return

    original = app_module.tool_preferences

    def tool_preferences_with_actions() -> None:
        st = app_module.st
        original_text_area = st.text_area
        original_text_input = st.text_input
        original_data_editor = st.data_editor
        original_expander = st.expander
        original_caption = st.caption
        original_warning = st.warning
        original_download_button = st.download_button

        captured = {
            "visible_output": "",
            "employee": "",
            "edited": None,
            "general_note": "",
            "actions_rendered": False,
        }

        def live_text_area(label, *args, **kwargs):
            if label == HIDDEN_OUTPUT_LABEL:
                if "value" in kwargs:
                    return kwargs["value"]
                if args:
                    return args[0]
                return ""

            if label == VISIBLE_OUTPUT_LABEL:
                value = kwargs.get("value", args[0] if args else "")
                captured["visible_output"] = str(value or "")
                key = kwargs.get("key")
                if key:
                    st.session_state[key] = value
            elif label == "הערה כללית להגשה":
                value = original_text_area(label, *args, **kwargs)
                captured["general_note"] = str(value or "")
                return value
            return original_text_area(label, *args, **kwargs)

        def capture_text_input(label, *args, **kwargs):
            value = original_text_input(label, *args, **kwargs)
            if kwargs.get("key") == "preferences_employee":
                captured["employee"] = str(value or "")
            return value

        def capture_data_editor(data, *args, **kwargs):
            edited = original_data_editor(data, *args, **kwargs)
            try:
                required = {"תאריך", "חופש", "הערה אישית"}
                has_block = "חסימה" in edited.columns or "חסימת תורנות מלאה" in edited.columns
                if required.issubset(set(edited.columns)) and has_block:
                    captured["edited"] = edited
            except Exception:
                pass
            return edited

        def simplified_expander(label, *args, **kwargs):
            if label == HIDDEN_EXPANDER_LABEL:
                return nullcontext()
            return original_expander(label, *args, **kwargs)

        def filtered_caption(body, *args, **kwargs):
            if str(body).strip() in HIDDEN_CAPTIONS:
                return None
            return original_caption(body, *args, **kwargs)

        def filtered_warning(body, *args, **kwargs):
            if str(body).strip() in HIDDEN_WARNINGS:
                return None
            return original_warning(body, *args, **kwargs)

        def reviewed_download_button(label, *args, **kwargs):
            file_name = str(kwargs.get("file_name", "") or "")
            is_preferences_download = file_name.startswith("העדפות_") and file_name.endswith(".xlsx")

            if not is_preferences_download:
                return original_download_button(label, *args, **kwargs)

            if captured["actions_rendered"]:
                return None
            captured["actions_rendered"] = True

            match = _MONTH_FROM_FILENAME.search(file_name)
            year = int(match.group(1)) if match else None
            month = int(match.group(2)) if match else None
            employee = str(captured.get("employee") or "").strip()
            edited = captured.get("edited")
            general_note = str(captured.get("general_note") or "").strip()
            ready = bool(employee and edited is not None and year is not None and month is not None)

            _render_copy_button(captured["visible_output"])

            if not ready:
                return None

            signature = _submission_signature(employee, year, month, edited, general_note)
            preview_key = f"preferences_preview_signature_{year}_{month}"
            reviewed = st.session_state.get(preview_key) == signature

            if st.button(
                "הצג לפני אישור",
                width="stretch",
                key=f"preview_preferences_{year}_{month}",
            ):
                st.session_state[preview_key] = signature
                reviewed = True

            if not reviewed:
                st.caption("לפני הגשה או הורדת CSV יש לעבור על התצוגה ולאשר שהמידע נכון.")
                return None

            _render_preview(st, employee, edited, general_note)

            sheets_ready = configured(st)
            if st.button(
                "הגש העדפות",
                type="primary",
                width="stretch",
                key=f"submit_preferences_{year}_{month}",
                disabled=not sheets_ready,
            ):
                try:
                    submission_edited = _real_rows(edited)
                    values = submit_preferences(
                        st,
                        employee,
                        year,
                        month,
                        submission_edited,
                        general_note=general_note,
                    )
                    display_month = f"{month:02d}-{year:04d}"
                    st.success(f"ההעדפות של {values[1]} לחודש {display_month} נקלטו בהצלחה.")
                except Exception as exc:
                    st.error(f"הגשת ההעדפות נכשלה: {exc}")

            if not sheets_ready:
                st.caption("הגשה למאגר תופעל לאחר השלמת חיבור Google Sheets של המערכת.")

            csv_data = _build_csv(employee, year, month, edited, general_note)
            original_download_button(
                "הורד קובץ CSV",
                data=csv_data,
                file_name=f"העדפות_{employee}_{year}_{month:02d}.csv",
                mime="text/csv; charset=utf-8",
                width="stretch",
                key=f"download_preferences_csv_{year}_{month}_{employee}",
            )
            return None

        st.text_area = live_text_area
        st.text_input = capture_text_input
        st.data_editor = capture_data_editor
        st.expander = simplified_expander
        st.caption = filtered_caption
        st.warning = filtered_warning
        st.download_button = reviewed_download_button
        try:
            original()
        finally:
            st.text_area = original_text_area
            st.text_input = original_text_input
            st.data_editor = original_data_editor
            st.expander = original_expander
            st.caption = original_caption
            st.warning = original_warning
            st.download_button = original_download_button

    app_module.tool_preferences = tool_preferences_with_actions
    app_module._preferences_output_override_installed = True
