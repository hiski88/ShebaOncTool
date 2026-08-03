"""Google Calendar compatibility wrapper with canonical OAuth state decoding."""
from __future__ import annotations

import base64

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
