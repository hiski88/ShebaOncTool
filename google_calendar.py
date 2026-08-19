"""Google Calendar compatibility wrapper with canonical OAuth state decoding."""
from __future__ import annotations

import base64
from datetime import datetime
from zoneinfo import ZoneInfo

import google_calendar_legacy as _legacy


def _encode_part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_part(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    decoded = base64.urlsafe_b64decode(value + padding)
    if _encode_part(decoded) != value:
        raise ValueError("Non-canonical base64url encoding")
    return decoded


_legacy._encode_part = _encode_part
_legacy._decode_part = _decode_part

for _name in dir(_legacy):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_legacy, _name)

_new_oauth_state = _legacy._new_oauth_state
_valid_oauth_state = _legacy._valid_oauth_state


def list_readable_calendars(service) -> list[dict[str, str]]:
    calendars: list[dict[str, str]] = []
    page_token = None
    while True:
        response = service.calendarList().list(pageToken=page_token).execute()
        for item in response.get("items", []):
            if item.get("accessRole") not in {"reader", "writer", "owner"}:
                continue
            summary = item.get("summaryOverride") or item.get("summary") or item["id"]
            calendars.append(
                {
                    "id": item["id"],
                    "summary": summary,
                    "label": summary + (" (ראשי)" if item.get("primary") else ""),
                    "primary": bool(item.get("primary", False)),
                }
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    calendars.sort(key=lambda item: (not item["primary"], item["summary"]))
    return calendars


def read_calendar_events(service, calendars: list[dict[str, str]], year: int, month: int, timezone_name: str = "Asia/Jerusalem") -> dict[str, list[str]]:
    if len(calendars) > 2:
        raise ValueError("ניתן לטעון עד שני יומנים בכל פעם.")

    tz = ZoneInfo(timezone_name)
    start = datetime(year, month, 1, tzinfo=tz)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        end = datetime(year, month + 1, 1, tzinfo=tz)

    grouped: dict[str, list[str]] = {}
    for calendar in calendars:
        page_token = None
        while True:
            response = service.events().list(
                calendarId=calendar["id"],
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            ).execute()
            for item in response.get("items", []):
                if item.get("status") == "cancelled":
                    continue
                start_value = item.get("start", {})
                title = item.get("summary") or "אירוע ללא כותרת"
                calendar_name = calendar.get("summary") or "יומן"
                if start_value.get("date"):
                    date_key = start_value["date"]
                    label = f"{title} ({calendar_name})"
                elif start_value.get("dateTime"):
                    event_dt = datetime.fromisoformat(start_value["dateTime"].replace("Z", "+00:00")).astimezone(tz)
                    date_key = event_dt.date().isoformat()
                    label = f"{event_dt.strftime('%H:%M')} - {title} ({calendar_name})"
                else:
                    continue
                grouped.setdefault(date_key, [])
                if label not in grouped[date_key]:
                    grouped[date_key].append(label)
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    return grouped
