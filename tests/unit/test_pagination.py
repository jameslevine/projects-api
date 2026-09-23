import base64
import json
from typing import Any

import pytest

from projects_api.api.pagination import decode_cursor, encode_cursor
from projects_api.domain.exceptions import InvalidCursorError

OWNER = "key-alice"


def _key(owner: str = OWNER) -> dict[str, Any]:
    return {
        "PK": {"S": "PROJECT#prj_" + "a" * 32},
        "SK": {"S": "META"},
        "GSI1PK": {"S": f"OWNER#{owner}"},
        "GSI1SK": {"S": "PROJECT#2026-09-23T10:00:00+00:00#prj_" + "a" * 32},
    }


def _token(obj: Any) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def test_round_trip_preserves_key() -> None:
    token = encode_cursor(_key())
    assert decode_cursor(token, OWNER) == _key()


def test_token_is_url_safe_without_padding() -> None:
    token = encode_cursor(_key())
    assert "=" not in token
    assert all(c.isalnum() or c in "-_" for c in token), token


def test_token_for_other_owner_is_rejected() -> None:
    token = encode_cursor(_key("key-bob"))
    with pytest.raises(InvalidCursorError):
        decode_cursor(token, OWNER)
    assert decode_cursor(token, "key-bob") == _key("key-bob")


@pytest.mark.parametrize(
    "token",
    [
        "",
        "not base64 !!!",
        "%%%%",
        base64.urlsafe_b64encode(b"\xff\xfe not utf8").decode(),
        _token("just a string"),
        _token(["PK", "SK"]),
        _token(42),
        _token({}),
        _token({k: v for k, v in _key().items() if k != "SK"}),  # missing key
        _token({**_key(), "extra": {"S": "x"}}),  # extra key
        _token({**_key(), "PK": "PROJECT#raw-string"}),  # untyped value
        _token({**_key(), "SK": {"N": "1"}}),  # wrong DynamoDB type
        _token({**_key(), "GSI1SK": {"S": "x", "N": "1"}}),  # two types
        _token({**_key(), "GSI1PK": {"S": "OWNER#"}}),  # owner prefix only
        _token({**_key(), "GSI1PK": {"S": f"owner#{OWNER}"}}),  # case differs
        "A" * 2000,  # oversized
    ],
)
def test_malformed_tokens_are_rejected(token: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(token, OWNER)


def test_tampered_token_is_rejected() -> None:
    token = encode_cursor(_key())
    # Truncating a token cannot leave a valid JSON object, so it must fail the checks.
    with pytest.raises(InvalidCursorError):
        decode_cursor(token[:-4], OWNER)


def test_padded_token_is_accepted() -> None:
    token = encode_cursor(_key())
    padded = token + "=" * (-len(token) % 4)
    assert decode_cursor(padded, OWNER) == _key()


def test_error_message_is_the_public_detail() -> None:
    assert str(InvalidCursorError()) == "nextToken is invalid or expired."
