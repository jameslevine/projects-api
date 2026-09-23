"""End-to-end through FastAPI with a moto DynamoDB table.

Two transports are exercised:
  * TestClient (local mode, identity from the X-Api-Key-Id header)
  * the Lambda `handler` with a synthetic API Gateway REST event (identity from apiKeyId)
"""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from projects_api.api import deps
from projects_api.config import Settings, get_settings
from projects_api.repositories.projects import ProjectRepository
from tests.conftest import TABLE_NAME


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


HEADERS = {"X-Api-Key-Id": "key-alice"}


def test_health_is_public(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_project_returns_201_with_body_and_location(client: TestClient) -> None:
    r = client.post("/v1/projects", json={"name": "My Agent", "type": "agent"}, headers=HEADERS)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "My Agent"
    assert body["type"] == "agent"
    assert body["status"] == "CREATED"
    assert body["ownerId"] == "key-alice"
    assert body["projectId"].startswith("prj_")
    assert r.headers["Location"] == f"/v1/projects/{body['projectId']}"


def test_duplicate_name_returns_409_problem(client: TestClient) -> None:
    client.post("/v1/projects", json={"name": "Shared Name", "type": "web"}, headers=HEADERS)
    r = client.post(
        "/v1/projects",
        json={"name": " shared   name ", "type": "mcp"},
        headers={"X-Api-Key-Id": "key-bob"},
    )
    assert r.status_code == 409
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 409
    assert body["title"] == "Project name already exists"
    assert body["instance"] == "/v1/projects"


@pytest.mark.parametrize(
    "payload, field",
    [
        ({"name": "ab", "type": "web"}, "name"),
        ({"name": "x" * 64, "type": "web"}, "name"),
        ({"name": "bad/name", "type": "web"}, "name"),
        ({"name": "-bad", "type": "web"}, "name"),
        ({"name": "fine name", "type": "database"}, "type"),
        ({"name": "fine name"}, "type"),
        ({"type": "web"}, "name"),
        ({"name": "fine name", "type": "web", "extra": 1}, "extra"),
    ],
)
def test_validation_failures_return_400_problem(
    client: TestClient, payload: dict[str, Any], field: str
) -> None:
    r = client.post("/v1/projects", json=payload, headers=HEADERS)
    assert r.status_code == 400, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["title"] == "Invalid request"
    assert any(e["field"] == field for e in body["errors"]), body


def test_missing_identity_returns_401(client: TestClient) -> None:
    r = client.post("/v1/projects", json={"name": "no identity", "type": "web"})
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")


def test_malformed_json_returns_400(client: TestClient) -> None:
    r = client.post(
        "/v1/projects", content="{not json", headers={**HEADERS, "content-type": "application/json"}
    )
    assert r.status_code == 400


# -- Lambda transport -------------------------------------------------------------


class _Ctx:
    aws_request_id = "req-123"
    function_name = "projects-api"
    memory_limit_in_mb = 512
    invoked_function_arn = "arn:aws:lambda:eu-west-2:123456789012:function:projects-api"


def _apigw_event(
    method: str, path: str, body: dict[str, Any] | None, api_key_id: str | None
) -> dict[str, Any]:
    return {
        "resource": "/{proxy+}",
        "path": path,
        "httpMethod": method,
        "headers": {
            "content-type": "application/json",
            "Host": "abc.execute-api.eu-west-2.amazonaws.com",
        },
        "multiValueHeaders": {},
        "queryStringParameters": None,
        "multiValueQueryStringParameters": None,
        "pathParameters": {"proxy": path.lstrip("/")},
        "stageVariables": None,
        "requestContext": {
            "resourceId": "abc123",
            "resourcePath": "/{proxy+}",
            "httpMethod": method,
            "path": f"/live{path}",
            "stage": "live",
            "requestId": "req-123",
            "identity": {"apiKeyId": api_key_id, "sourceIp": "127.0.0.1"},
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


def test_lambda_handler_uses_api_key_id_as_owner(client: TestClient) -> None:
    from projects_api.main import handler

    resp = handler(
        _apigw_event("POST", "/v1/projects", {"name": "via lambda", "type": "web"}, "k9x8y7"),
        _Ctx(),
    )
    assert resp["statusCode"] == 201, resp
    body = json.loads(resp["body"])
    assert body["ownerId"] == "k9x8y7"
    assert resp["headers"]["location"] == f"/v1/projects/{body['projectId']}"


def test_lambda_handler_conflict_carries_request_id(client: TestClient) -> None:
    from projects_api.main import handler

    handler(_apigw_event("POST", "/v1/projects", {"name": "dupe", "type": "web"}, "k1"), _Ctx())
    resp = handler(
        _apigw_event("POST", "/v1/projects", {"name": "DUPE", "type": "web"}, "k2"), _Ctx()
    )
    assert resp["statusCode"] == 409
    body = json.loads(resp["body"])
    assert body["requestId"] == "req-123"
    assert resp["headers"]["x-request-id"] == "req-123"
