"""Opaque cursor tokens for list endpoints.

A `nextToken` is the URL-safe base64 (padding stripped) of the compact JSON of the raw
DynamoDB `LastEvaluatedKey`. Clients treat it as opaque. Decoding checks the shape (exactly
the four key attributes, all strings) and that the partition key belongs to the caller, so a
token can never be used to page through another owner's projects.
"""

import base64
import json
from typing import Any

from projects_api.domain.exceptions import InvalidCursorError
from projects_api.repositories.projects import owner_gsi1pk

CURSOR_KEYS = frozenset({"PK", "SK", "GSI1PK", "GSI1SK"})
_MAX_TOKEN_LENGTH = 1024


def encode_cursor(key: dict[str, Any]) -> str:
    raw = json.dumps(key, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(token: str, owner_id: str) -> dict[str, Any]:
    """Return the DynamoDB key encoded in `token`, or raise InvalidCursorError."""
    if not token or len(token) > _MAX_TOKEN_LENGTH:
        raise InvalidCursorError()
    padded = token + "=" * (-len(token) % 4)
    try:
        key = json.loads(base64.urlsafe_b64decode(padded))
    except ValueError as exc:  # binascii.Error and JSONDecodeError are ValueErrors
        raise InvalidCursorError() from exc
    if not isinstance(key, dict) or set(key) != CURSOR_KEYS:
        raise InvalidCursorError()
    for attr in key.values():
        if not (isinstance(attr, dict) and set(attr) == {"S"} and isinstance(attr["S"], str)):
            raise InvalidCursorError()
    if key["GSI1PK"]["S"] != owner_gsi1pk(owner_id):
        raise InvalidCursorError()
    return key
