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
from projects_api.domain.models import Project, ProjectType
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


# -- GET /v1/projects/{projectId} ---------------------------------------------------


def _create(client: TestClient, name: str, headers: dict[str, str]) -> dict[str, Any]:
    r = client.post("/v1/projects", json={"name": name, "type": "agent"}, headers=headers)
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def _assert_not_found(r: Any) -> None:
    assert r.status_code == 404, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 404
    assert body["title"] == "Project not found"
    assert body["type"].endswith("/project-not-found")


def test_get_project_returns_200_for_owner_with_same_body_as_create(client: TestClient) -> None:
    created = _create(client, "Readable", HEADERS)
    r = client.get(f"/v1/projects/{created['projectId']}", headers=HEADERS)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == created


def test_get_project_returns_404_for_other_owner(client: TestClient) -> None:
    created = _create(client, "Alice Only", HEADERS)
    r = client.get(f"/v1/projects/{created['projectId']}", headers={"X-Api-Key-Id": "key-bob"})
    _assert_not_found(r)
    assert r.json()["instance"] == f"/v1/projects/{created['projectId']}"
    # Still readable by the owner: the 404 above was about identity, not existence.
    assert client.get(f"/v1/projects/{created['projectId']}", headers=HEADERS).status_code == 200


def test_get_project_returns_404_for_unknown_well_formed_id(client: TestClient) -> None:
    unknown = Project.new(
        name="never stored", type_=ProjectType.AGENT, owner_id="key-alice"
    ).project_id
    _assert_not_found(client.get(f"/v1/projects/{unknown}", headers=HEADERS))


@pytest.mark.parametrize(
    "bad_id",
    [
        "prj_doesnotexist",
        "prj_" + "0" * 31,
        "prj_" + "0" * 33,
        "prj_" + "G" * 32,
        "prj_" + "A" * 32,  # upper-case hex is not what Project.new produces
        "0" * 32,
        "usr_" + "0" * 32,
        "not-an-id",
    ],
)
def test_get_project_returns_404_not_400_for_malformed_id_without_touching_the_table(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, bad_id: str
) -> None:
    def _must_not_be_called(self: ProjectRepository, project_id: str) -> Project:
        raise AssertionError(f"repository.get was called with {project_id!r}")

    monkeypatch.setattr(ProjectRepository, "get", _must_not_be_called)
    _assert_not_found(client.get(f"/v1/projects/{bad_id}", headers=HEADERS))


def test_get_project_requires_identity(client: TestClient) -> None:
    created = _create(client, "Needs Identity", HEADERS)
    r = client.get(f"/v1/projects/{created['projectId']}")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")


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


def test_lambda_handler_get_project_returns_200_for_owner(client: TestClient) -> None:
    from projects_api.main import handler

    created = handler(
        _apigw_event("POST", "/v1/projects", {"name": "get via lambda", "type": "web"}, "k-own"),
        _Ctx(),
    )
    assert created["statusCode"] == 201, created
    project = json.loads(created["body"])
    path = f"/v1/projects/{project['projectId']}"

    resp = handler(_apigw_event("GET", path, None, "k-own"), _Ctx())
    assert resp["statusCode"] == 200, resp
    assert json.loads(resp["body"]) == project

    other = handler(_apigw_event("GET", path, None, "k-other"), _Ctx())
    assert other["statusCode"] == 404, other
    assert json.loads(other["body"])["title"] == "Project not found"
    assert other["headers"]["content-type"].startswith("application/problem+json")
