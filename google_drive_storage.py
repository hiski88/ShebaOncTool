"""Google Drive access for final schedule storage.

Uses the same service account configured for Google Sheets, but requests a
Drive OAuth scope only when Drive access is needed. This keeps the existing
Sheets integration unchanged while allowing Tool 3/4 to work with the shared
Final Schedules folder.
"""
from __future__ import annotations

from google.oauth2 import service_account
from googleapiclient.discovery import build

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def _google_section(st):
    try:
        return st.secrets.get("google_sheets", {})
    except Exception:
        return {}


def _service_account_info(st) -> dict:
    section = _google_section(st)
    account = dict(section.get("service_account", {}))
    if not account:
        raise RuntimeError("חיבור Google טרם הוגדר באפליקציה.")
    if "private_key" in account:
        account["private_key"] = str(account["private_key"]).replace("\\n", "\n")
    return account


def final_schedules_folder_id(st) -> str:
    try:
        folder_id = str(st.secrets.get("FINAL_SCHEDULES_DRIVE_FOLDER_ID", "")).strip()
    except Exception:
        folder_id = ""
    if not folder_id:
        raise RuntimeError("FINAL_SCHEDULES_DRIVE_FOLDER_ID לא הוגדר ב-Streamlit Secrets.")
    return folder_id


def drive_service(st):
    """Build an authenticated Drive v3 client using the existing service account."""
    credentials = service_account.Credentials.from_service_account_info(
        _service_account_info(st),
        scopes=DRIVE_SCOPES,
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def verify_final_schedules_access(st) -> dict:
    """Return minimal folder metadata and fail clearly if the app cannot access it."""
    service = drive_service(st)
    folder_id = final_schedules_folder_id(st)
    return service.files().get(
        fileId=folder_id,
        fields="id,name,mimeType,capabilities(canAddChildren)",
        supportsAllDrives=True,
    ).execute()
