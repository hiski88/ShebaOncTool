"""Google Drive access for final schedule storage.

Uses the same service account configured for Google Sheets, but requests a
Drive OAuth scope only when Drive access is needed. This keeps the existing
Sheets integration unchanged while allowing Tool 3/4 to work with the shared
Final Schedules folder.
"""
from __future__ import annotations

from io import BytesIO
import re

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
_FINAL_SCHEDULE_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})_V(?P<version>\d+)(?P<suffix>.*)\.(?P<ext>xls|xlsx)$", re.IGNORECASE)


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


def list_year_files(st, year: int) -> list[dict]:
    """List non-folder files directly inside the requested year folder."""
    service = drive_service(st)
    folder = ensure_year_folder(st, year)
    query = f"'{folder['id']}' in parents and trashed = false and mimeType != '{FOLDER_MIME_TYPE}'"
    files: list[dict] = []
    page_token = None
    while True:
        response = service.files().list(
            q=query,
            fields="nextPageToken,files(id,name,mimeType,size,createdTime,modifiedTime)",
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return files


def parse_final_schedule_filename(filename: str) -> dict | None:
    """Parse the standard YYYY-MM_VN.xls/xlsx naming convention.

    A suffix after the version is tolerated so Tool 4 can also discover files
    placed manually in Drive, e.g. 2026-09_V2_final.xlsx.
    """
    match = _FINAL_SCHEDULE_RE.match(str(filename or "").strip())
    if not match:
        return None
    result = match.groupdict()
    return {
        "year": int(result["year"]),
        "month": int(result["month"]),
        "version": int(result["version"]),
        "extension": result["ext"].lower(),
    }


def next_schedule_version(st, year: int, month: int) -> int:
    """Return one more than the highest Drive version for the requested month."""
    highest = 0
    for item in list_year_files(st, year):
        parsed = parse_final_schedule_filename(item.get("name", ""))
        if not parsed:
            continue
        if parsed["year"] == int(year) and parsed["month"] == int(month):
            highest = max(highest, parsed["version"])
    return highest + 1


def build_schedule_filename(year: int, month: int, version: int, extension: str) -> str:
    ext = str(extension or "").lower().lstrip(".")
    if ext not in {"xls", "xlsx"}:
        raise ValueError("ניתן לשמור רק קבצי XLS או XLSX.")
    return f"{int(year):04d}-{int(month):02d}_V{int(version)}.{ext}"


def upload_final_schedule(st, year: int, month: int, original_filename: str, content: bytes) -> dict:
    """Store original bytes under the next standard versioned filename.

    Version is derived from the files that actually exist in Drive, not from
    the metadata index, so files placed manually in Drive are respected too.
    """
    original = str(original_filename or "").strip()
    extension = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if extension not in {"xls", "xlsx"}:
        raise ValueError("ניתן להעלות רק קבצי XLS או XLSX.")
    if not content:
        raise ValueError("הקובץ שהועלה ריק.")

    service = drive_service(st)
    folder = ensure_year_folder(st, year)
    version = next_schedule_version(st, year, month)
    stored_filename = build_schedule_filename(year, month, version, extension)

    # Re-check the exact target name just before writing. Google Drive permits
    # duplicate names, so this guard avoids an accidental collision if another
    # upload occurred between preview and save.
    while True:
        safe_name = _escape_drive_query(stored_filename)
        query = f"'{folder['id']}' in parents and trashed = false and name = '{safe_name}'"
        existing = service.files().list(
            q=query,
            fields="files(id,name)",
            pageSize=10,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute().get("files", [])
        if not existing:
            break
        version += 1
        stored_filename = build_schedule_filename(year, month, version, extension)

    mimetype = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if extension == "xlsx"
        else "application/vnd.ms-excel"
    )
    media = MediaIoBaseUpload(BytesIO(content), mimetype=mimetype, resumable=False)
    created = service.files().create(
        body={"name": stored_filename, "parents": [folder["id"]]},
        media_body=media,
        fields="id,name,mimeType,size,createdTime,webViewLink",
        supportsAllDrives=True,
    ).execute()
    return {
        **created,
        "year": int(year),
        "month": int(month),
        "version": int(version),
        "extension": extension,
        "original_filename": original,
        "stored_filename": stored_filename,
        "year_folder_id": folder["id"],
    }


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
