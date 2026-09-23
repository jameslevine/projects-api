"""Request correlation (S3-302): `X-Request-Id` on every response, matching problem bodies and logs.

Both transports are exercised: TestClient (no gateway, so the id is a generated UUID or the
echoed client header) and the Lambda `handler` (the API Gateway `requestContext.requestId` wins
over the Lambda `aws_request_id`).
"""

import io
import json
import logging
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from projects_api.api import deps
from projects_api.config import Settings, get_settings
from projects_api.repositories.projects import ProjectRepository
from tests.conftest import TABLE_NAME
from tests.integration.test_projects_api import _apigw_event, _Ctx


@pytest.fixture
def client(dynamodb_table: Any) -> Iterator[TestClient]:
    from projects_api.main import app

    settings = Settings(env="local", table_name=TABLE_NAME)
    repo = ProjectRepository(settings, client=dynamodb_table)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[deps.get_repository] = lambda: repo
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


HEADERS = {"X-Api-Key-Id": "key-corr"}


def _is_uuid4(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 4 and str(parsed) == value


def _completed_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage() == "request completed"]


# -- TestClient transport ------------------------------------------------------------


def test_every_response_gets_a_uuid4_request_id_when_none_is_sent(client: TestClient) -> None:
    responses = [
        client.get("/health"),
        client.post("/v1/projects", json={"name": "corr one", "type": "web"}, headers=HEADERS),
        client.get("/v1/does-not-exist"),
        client.post("/v1/projects", json={"name": "no identity", "type": "web"}),
    ]
    ids = [r.headers["x-request-id"] for r in responses]
    assert [r.status_code for r in responses] == [200, 201, 404, 401]
    assert all(_is_uuid4(rid) for rid in ids), ids
    assert len(set(ids)) == len(ids), "ids must be generated per request"


def test_incoming_request_id_header_is_echoed(client: TestClient) -> None:
    r = client.get("/health", headers={"X-Request-Id": "client-abc-123"})
    assert r.headers["x-request-id"] == "client-abc-123"


@pytest.mark.parametrize("header", ["x" * 129, "   ", "bad\x00id"])
def test_unusable_request_id_headers_are_replaced(client: TestClient, header: str) -> None:
    r = client.get("/health", headers={"X-Request-Id": header})
    assert r.status_code == 200
    assert _is_uuid4(r.headers["x-request-id"])


def test_problem_body_request_id_matches_header_locally(client: TestClient) -> None:
    client.post("/v1/projects", json={"name": "taken locally", "type": "web"}, headers=HEADERS)
    conflict = client.post(
        "/v1/projects", json={"name": "Taken Locally", "type": "mcp"}, headers=HEADERS
    )
    missing = client.get("/v1/projects/prj_" + "0" * 32, headers=HEADERS)
    for r, code in ((conflict, 409), (missing, 404)):
        assert r.status_code == code, r.text
        assert r.headers["content-type"].startswith("application/problem+json")
        assert r.json()["requestId"] == r.headers["x-request-id"]
        assert _is_uuid4(r.json()["requestId"])


# -- Lambda transport --------------------------------------------------------------


def test_lambda_success_response_carries_gateway_request_id(client: TestClient) -> None:
    from projects_api.main import handler

    resp = handler(
        _apigw_event("POST", "/v1/projects", {"name": "gw id", "type": "web"}, "k-gw"), _Ctx()
    )
    assert resp["statusCode"] == 201, resp
    assert resp["headers"]["x-request-id"] == "apigw-req-1"
    assert _Ctx.aws_request_id != "apigw-req-1", "the test must tell the two ids apart"


def test_lambda_problem_bodies_match_gateway_request_id(client: TestClient) -> None:
    from projects_api.main import handler

    handler(_apigw_event("POST", "/v1/projects", {"name": "gw dupe", "type": "web"}, "k1"), _Ctx())
    conflict = handler(
        _apigw_event(
            "POST", "/v1/projects", {"name": "GW DUPE", "type": "web"}, "k2", request_id="gw-409"
        ),
        _Ctx(),
    )
    missing = handler(
        _apigw_event("GET", "/v1/projects/prj_" + "f" * 32, None, "k1", request_id="gw-404"),
        _Ctx(),
    )
    for resp, code, rid in ((conflict, 409, "gw-409"), (missing, 404, "gw-404")):
        assert resp["statusCode"] == code, resp
        assert resp["headers"]["x-request-id"] == rid
        assert json.loads(resp["body"])["requestId"] == rid


def test_lambda_falls_back_to_lambda_request_id_without_a_gateway_id(client: TestClient) -> None:
    from projects_api.main import handler

    resp = handler(_apigw_event("GET", "/health", None, None, request_id=None), _Ctx())
    assert resp["statusCode"] == 200
    assert resp["headers"]["x-request-id"] == _Ctx.aws_request_id


# -- Access log line -----------------------------------------------------------------


def test_access_log_line_has_fields_and_no_sensitive_data(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    secret_name = "Top Secret Project Name"
    secret_key = "sk-live-never-log-me"  # a fake value; the test asserts it is absent
    with caplog.at_level(logging.INFO):
        r = client.post(
            "/v1/projects",
            json={"name": secret_name, "type": "web"},
            headers={**HEADERS, "x-api-key": secret_key, "X-Request-Id": "log-req-1"},
        )
    assert r.status_code == 201, r.text

    records = _completed_records(caplog)
    assert len(records) == 1, [r.getMessage() for r in caplog.records]
    record = records[0]
    assert record.route == "/v1/projects"  # type: ignore[attr-defined]
    assert record.method == "POST"  # type: ignore[attr-defined]
    assert record.status == 201  # type: ignore[attr-defined]
    assert record.request_id == "log-req-1"  # type: ignore[attr-defined]
    assert record.owner_id is None  # type: ignore[attr-defined]  # no gateway locally
    assert record.duration_ms >= 0  # type: ignore[attr-defined]

    everything_logged = repr(vars(record))
    assert secret_name not in everything_logged
    assert secret_key not in everything_logged
    assert "x-api-key" not in everything_logged.lower()
    assert '"type": "web"' not in everything_logged


def test_access_log_line_for_lambda_has_owner_id_route_template_and_status(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    from projects_api.main import handler
    from projects_api.observability import logger

    # `correlation_id` is appended by the Powertools formatter (inject_lambda_context with
    # correlation_paths.API_GATEWAY_REST), so it only exists in the formatted JSON line, not on
    # the LogRecord. Capture the formatted output with a temporary handler using that formatter.
    formatted = io.StringIO()
    capture = logging.StreamHandler(formatted)
    capture.setFormatter(logger.registered_formatter)
    logger.addHandler(capture)
    try:
        with caplog.at_level(logging.INFO):
            resp = handler(
                _apigw_event(
                    "GET", "/v1/projects/prj_" + "a" * 32, None, "k-log", request_id="gw-log"
                ),
                _Ctx(),
            )
    finally:
        logger.removeHandler(capture)
    assert resp["statusCode"] == 404

    (record,) = _completed_records(caplog)
    assert record.route == "/v1/projects/{project_id}"  # type: ignore[attr-defined]
    assert record.method == "GET"  # type: ignore[attr-defined]
    assert record.status == 404  # type: ignore[attr-defined]
    assert record.owner_id == "k-log"  # type: ignore[attr-defined]
    assert record.request_id == "gw-log"  # type: ignore[attr-defined]

    emitted = [
        json.loads(line)
        for line in formatted.getvalue().splitlines()
        if '"message":"request completed"' in line
    ]
    (line,) = emitted
    assert line["correlation_id"] == "gw-log"
    assert line["function_request_id"] == _Ctx.aws_request_id  # the Lambda id, kept separately
