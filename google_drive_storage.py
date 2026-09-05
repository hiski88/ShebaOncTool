"""Google Drive access for final schedule storage.

Uses the same service account configured for Google Sheets, but requests a
Drive OAuth scope only when Drive access is needed. This keeps the existing
Sheets integration unchanged while allowing Tool 3/4 to work with the shared
Final Schedules folder.
"""
from __future__ import annotations

from io import BytesIO

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


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


def _escape_drive_query(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def ensure_year_folder(st, year: int) -> dict:
    """Return the requested year folder, creating it under Final Schedules when absent."""
    service = drive_service(st)
    root_id = final_schedules_folder_id(st)
    year_name = f"{int(year):04d}"
    safe_year = _escape_drive_query(year_name)
    query = (
        f"'{root_id}' in parents and trashed = false and "
        f"mimeType = '{FOLDER_MIME_TYPE}' and name = '{safe_year}'"
    )
    response = service.files().list(
        q=query,
        fields="files(id,name,mimeType)",
        pageSize=10,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    folders = response.get("files", [])
    if folders:
        return folders[0]

    return service.files().create(
        body={"name": year_name, "mimeType": FOLDER_MIME_TYPE, "parents": [root_id]},
        fields="id,name,mimeType",
        supportsAllDrives=True,
    ).execute()


def verify_drive_write_cycle(st, year: int) -> dict:
    """Create, read back and delete a tiny test file in the year's folder."""
    service = drive_service(st)
    folder = ensure_year_folder(st, year)
    payload = b"MedStaff Google Drive write test"
    test_file = None

    try:
        media = MediaIoBaseUpload(
            BytesIO(payload),
            mimetype="text/plain",
            resumable=False,
        )
        test_file = service.files().create(
            body={"name": "drive_test.txt", "parents": [folder["id"]]},
            media_body=media,
            fields="id,name,size",
            supportsAllDrives=True,
        ).execute()

        downloaded = service.files().get_media(
            fileId=test_file["id"],
            supportsAllDrives=True,
        ).execute()
        if downloaded != payload:
            raise RuntimeError("קובץ הבדיקה נוצר, אך התוכן שנקרא חזרה אינו תואם.")

        return {
            "folder_id": folder["id"],
            "folder_name": folder["name"],
            "file_id": test_file["id"],
            "file_name": test_file["name"],
        }
    finally:
        if test_file and test_file.get("id"):
            try:
                service.files().delete(
                    fileId=test_file["id"],
                    supportsAllDrives=True,
                ).execute()
            except Exception:
                pass
