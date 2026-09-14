"""Attach stable Worker ID to Tool 1 submissions while preserving legacy rows."""
from __future__ import annotations

import google_sheets_submissions as submissions


IDENTIFIED_WORKER_SESSION_KEY = "medstaff_identified_worker_v1"


def _current_worker_id(st) -> str:
    worker = st.session_state.get(IDENTIFIED_WORKER_SESSION_KEY)
    if isinstance(worker, dict):
        return str(worker.get("worker_id", "") or "").strip()
    return ""


def submit_preferences_with_identity(
    st,
    employee: str,
    year: int,
    month: int,
    edited,
    general_note: str = "",
    worker_id: str = "",
) -> list[str]:
    service, spreadsheet_id, sheet_name = submissions._service(st)
    stable_worker_id = str(worker_id or "").strip() or _current_worker_id(st)
    values = submissions._submission_values(
        employee,
        year,
        month,
        edited,
        general_note=general_note,
    ) + [stable_worker_id]

    result = service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A:I",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        includeValuesInResponse=True,
        responseValueRenderOption="FORMATTED_VALUE",
        body={"values": [values]},
    ).execute()

    updates = result.get("updates", {})
    stored_rows = updates.get("updatedData", {}).get("values", [])
    if stored_rows:
        stored = stored_rows[0]
    else:
        updated_range = str(updates.get("updatedRange", "") or "").strip()
        if not updated_range:
            raise RuntimeError("ההגשה נשלחה, אך Google Sheets לא החזיר את מיקום השורה שנכתבה.")
        check = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=updated_range,
            valueRenderOption="FORMATTED_VALUE",
        ).execute()
        stored = check.get("values", [[]])[0]

    padded = [str(item) for item in stored] + [""] * (9 - len(stored))
    if padded[:9] != values:
        raise RuntimeError("ההגשה נשלחה, אך לא ניתן היה לאמת שהמידע נקלט במלואו.")
    return values


def read_submissions_with_identity(st, year: int, month: int) -> list[dict[str, str]]:
    service, spreadsheet_id, sheet_name = submissions._service(st)
    response = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{sheet_name}'!A2:I",
        valueRenderOption="FORMATTED_VALUE",
    ).execute()

    month_value = f"{year:04d}-{month:02d}"
    indexed_rows = []
    for row_index, raw in enumerate(response.get("values", [])):
        values = [str(item) for item in raw] + [""] * (9 - len(raw))
        (
            submitted_at,
            employee,
            submitted_month,
            full_blocks,
            half_blocks,
            vacations,
            wants_duty,
            general_note,
            worker_id,
        ) = values[:9]
        if submitted_month.strip() != month_value or not employee.strip():
            continue
        item = {
            "זמן הגשה": submitted_at.strip(),
            "שם עובד": employee.strip(),
            "חודש": submitted_month.strip(),
            "חסימת תורנות מלאה": full_blocks.strip(),
            "חסימת תורנות חצי": half_blocks.strip(),
            "חופשים": vacations.strip(),
            "מעוניין בתורנות": wants_duty.strip(),
            "הערה כללית": general_note.strip(),
            "Worker ID": worker_id.strip(),
        }
        indexed_rows.append((submissions._submission_time(submitted_at), row_index, item))

    indexed_rows.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    return [entry[2] for entry in indexed_rows]


def install(app_module) -> None:
    """Patch consumers that imported submission functions by name."""
    if getattr(submissions, "_submission_identity_override_installed", False):
        return

    import preferences_output_overrides
    import tool2_submissions_overrides

    submissions.submit_preferences = submit_preferences_with_identity
    submissions.read_submissions = read_submissions_with_identity
    preferences_output_overrides.submit_preferences = submit_preferences_with_identity
    tool2_submissions_overrides.read_submissions = read_submissions_with_identity
    submissions._submission_identity_override_installed = True
