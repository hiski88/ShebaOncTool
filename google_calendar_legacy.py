from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta
from typing import Any, Iterable

from core import CalendarEvent

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]


def oauth_dependencies_available() -> bool:
    try:
        import streamlit  # noqa: F401
        from google_auth_oauthlib.flow import Flow  # noqa: F401
        from google.oauth2.credentials import Credentials  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
        return True
    except Exception:
        return False


def oauth_configured(st) -> bool:
    try:
        section = st.secrets["google_oauth"]
        return all(section.get(key) for key in ["client_id", "client_secret", "redirect_uri"])
    except Exception:
        return False


def _state_secret(st) -> bytes:
    section = st.secrets["google_oauth"]
    value = section.get("state_secret") or section["client_secret"]
    return str(value).encode("utf-8")


def _encode_part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_part(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _new_oauth_state(st) -> str:
    payload = f"{int(time.time())}.{secrets.token_urlsafe(18)}".encode("utf-8")
    signature = hmac.new(_state_secret(st), payload, hashlib.sha256).digest()
    return f"{_encode_part(payload)}.{_encode_part(signature)}"


def _valid_oauth_state(st, value: str | None, max_age_seconds: int = 900) -> bool:
    if not value or "." not in value:
        return False
    try:
        payload_part, signature_part = value.split(".", 1)
        payload = _decode_part(payload_part)
        signature = _decode_part(signature_part)
        expected = hmac.new(_state_secret(st), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return False
        issued_at = int(payload.decode("utf-8").split(".", 1)[0])
        age = int(time.time()) - issued_at
        return 0 <= age <= max_age_seconds
    except Exception:
        return False


def _flow(st, state: str | None = None):
    from google_auth_oauthlib.flow import Flow

    section = st.secrets["google_oauth"]
    client_config = {
        "web": {
            "client_id": section["client_id"],
            "client_secret": section["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [section["redirect_uri"]],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=GOOGLE_SCOPES, state=state)
    flow.redirect_uri = section["redirect_uri"]
    return flow


def get_credentials(st):
    from google.oauth2.credentials import Credentials

    raw = st.session_state.get("google_credentials")
    if not raw:
        return None
    try:
        info = json.loads(raw) if isinstance(raw, str) else raw
        credentials = Credentials.from_authorized_user_info(info, scopes=GOOGLE_SCOPES)
        if credentials.expired and credentials.refresh_token:
            from google.auth.transport.requests import Request

            credentials.refresh(Request())
            st.session_state["google_credentials"] = credentials.to_json()
        return credentials
    except Exception:
        st.session_state.pop("google_credentials", None)
        return None


def handle_oauth_callback(st) -> tuple[bool, str | None]:
    if not oauth_configured(st) or not oauth_dependencies_available():
        return False, None
    code = st.query_params.get("code")
    returned_state = st.query_params.get("state")
    if not code:
        return False, None

    expected_state = st.session_state.get("google_oauth_state")
    if not _valid_oauth_state(st, returned_state):
        return False, "החיבור ליומן נעצר משום שמזהה האבטחה אינו תקין או שפג תוקפו. יש להתחיל את החיבור מחדש."
    if expected_state and returned_state != expected_state:
        return False, "החיבור ליומן נעצר משום שמזהה האבטחה לא תאם. יש להתחיל את החיבור מחדש."

    try:
        flow = _flow(st, state=returned_state)
        flow.fetch_token(code=code)
        st.session_state["google_credentials"] = flow.credentials.to_json()
        st.session_state.pop("google_oauth_state", None)
        st.query_params.clear()
        return True, None
    except Exception as exc:
        return False, f"לא ניתן היה להשלים את החיבור ליומן: {exc}"


def authorization_url(st) -> str:
    state = _new_oauth_state(st)
    st.session_state["google_oauth_state"] = state
    flow = _flow(st, state=state)
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return url


def disconnect(st) -> None:
    st.session_state.pop("google_credentials", None)
    st.session_state.pop("google_oauth_state", None)


def build_service(credentials):
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def list_writable_calendars(service) -> list[dict[str, str]]:
    calendars: list[dict[str, str]] = []
    page_token = None
    while True:
        response = service.calendarList().list(pageToken=page_token).execute()
        for item in response.get("items", []):
            if item.get("accessRole") in {"owner", "writer"}:
                calendars.append(
                    {
                        "id": item["id"],
                        "summary": item.get("summaryOverride") or item.get("summary") or item["id"],
                        "primary": bool(item.get("primary", False)),
                    }
                )
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    calendars.sort(key=lambda item: (not item["primary"], item["summary"]))
    return calendars


def _google_event_body(event: CalendarEvent, timezone_name: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": event.uid.split("@", 1)[0],
        "summary": event.title,
        "description": event.description,
    }
    if event.all_day:
        body["start"] = {"date": event.event_date.isoformat()}
        body["end"] = {"date": (event.event_date + timedelta(days=1)).isoformat()}
    else:
        assert event.start is not None and event.end is not None
        body["start"] = {"dateTime": event.start.isoformat(), "timeZone": timezone_name}
        body["end"] = {"dateTime": event.end.isoformat(), "timeZone": timezone_name}
    return body


def create_events(
    service,
    calendar_id: str,
    events: Iterable[CalendarEvent],
    timezone_name: str = "Asia/Jerusalem",
) -> dict[str, Any]:
    from googleapiclient.errors import HttpError

    created = 0
    existing = 0
    errors: list[str] = []
    links: list[str] = []
    for event in events:
        try:
            response = service.events().insert(
                calendarId=calendar_id,
                body=_google_event_body(event, timezone_name),
                sendUpdates="none",
            ).execute()
            created += 1
            if response.get("htmlLink"):
                links.append(response["htmlLink"])
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status == 409:
                existing += 1
            else:
                errors.append(f"{event.event_date.isoformat()} - {event.title}: {exc}")
        except Exception as exc:
            errors.append(f"{event.event_date.isoformat()} - {event.title}: {exc}")
    return {"created": created, "existing": existing, "errors": errors, "links": links}
