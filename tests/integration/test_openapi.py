"""Contract test for `/v1/openapi.json`.

The document is what generated clients are built from, so it must be valid OpenAPI 3.1 and
describe the wire behaviour exactly: problem+json on every error, the API key scheme, readable
operationIds. The last test checks the `Problem` schema against real error responses.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from projects_api.api import deps
from projects_api.api.errors import Problem
from projects_api.api.openapi import PROBLEM_REF, SECURITY_SCHEME
from projects_api.config import get_settings

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    from projects_api.main import app

    with TestClient(app) as client:
        response = client.get("/v1/openapi.json")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _operations(spec: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method in HTTP_METHODS:
                yield path, method, operation


def test_spec_is_valid_openapi_31(spec: dict[str, Any]) -> None:
    assert spec["openapi"].startswith("3.1")
    validate(spec)  # raises on any violation


def test_spec_has_description_and_relative_server(spec: dict[str, Any]) -> None:
    assert spec["info"]["description"].strip()
    assert [server["url"] for server in spec["servers"]] == ["/"]


def test_every_error_response_is_problem_json(spec: dict[str, Any]) -> None:
    assert "Problem" in spec["components"]["schemas"]
    seen = 0
    for path, method, operation in _operations(spec):
        for code, response in operation["responses"].items():
            if code.startswith("2"):
                continue
            seen += 1
            content = response.get("content", {})
            assert list(content) == ["application/problem+json"], (path, method, code, content)
            assert content["application/problem+json"]["schema"] == {"$ref": PROBLEM_REF}
    assert seen > 0


def test_no_422_and_no_fastapi_validation_schemas(spec: dict[str, Any]) -> None:
    for path, method, operation in _operations(spec):
        assert "422" not in operation["responses"], (path, method)
    assert "HTTPValidationError" not in spec["components"]["schemas"]
    assert "ValidationError" not in spec["components"]["schemas"]


def test_api_key_security_scheme_applies_everywhere_but_health(spec: dict[str, Any]) -> None:
    assert spec["components"]["securitySchemes"][SECURITY_SCHEME] == {
        "type": "apiKey",
        "in": "header",
        "name": "x-api-key",
        "description": "API Gateway API key attached to a usage plan.",
    }
    assert spec["security"] == [{SECURITY_SCHEME: []}]
    assert spec["paths"]["/health"]["get"]["security"] == []
    for path, method, operation in _operations(spec):
        if (path, method) != ("/health", "get"):
            assert "security" not in operation, (path, method)  # inherits the global requirement


def test_operation_ids_are_unique_and_readable(spec: dict[str, Any]) -> None:
    ids = [operation["operationId"] for _, _, operation in _operations(spec)]
    assert len(ids) == len(set(ids)), ids
    assert {"getHealth", "createProject", "getProject", "listProjects", "deleteProject"} <= set(ids)
    for operation_id in ids:
        assert operation_id.isidentifier() and "_" not in operation_id, operation_id


def test_create_project_has_examples(spec: dict[str, Any]) -> None:
    operation = spec["paths"]["/v1/projects"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["example"] == {
        "name": "my-first-agent",
        "type": "agent",
    }
    created = operation["responses"]["201"]
    assert "Location" in created["headers"]
    example = created["content"]["application/json"]["example"]
    assert example["projectId"].startswith("prj_")
    assert example["status"] == "CREATED"


def test_delete_project_is_204_without_content(spec: dict[str, Any]) -> None:
    operation = spec["paths"]["/v1/projects/{project_id}"]["delete"]
    assert operation["operationId"] == "deleteProject"
    assert "content" not in operation["responses"]["204"]
    assert "404" in operation["responses"]
    assert "requestBody" not in operation


@pytest.fixture
def non_local_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENV", "dev")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_openapi_json_is_served_outside_local_but_docs_are_not(non_local_env: None) -> None:
    from projects_api.main import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/v1/openapi.json").status_code == 200
        assert client.get("/v1/docs").status_code == 404


def test_problem_schema_matches_live_error_responses() -> None:
    from projects_api.main import app

    deps._repository.cache_clear()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            unauthenticated = client.post("/v1/projects", json={"name": "abc", "type": "web"})
            unknown = client.get("/v1/nope")
            invalid = client.post(
                "/v1/projects", json={"name": "ab"}, headers={"X-Api-Key-Id": "key-openapi"}
            )
    finally:
        deps._repository.cache_clear()

    for response, code in ((unauthenticated, 401), (unknown, 404), (invalid, 400)):
        assert response.status_code == code, response.text
        assert response.headers["content-type"].startswith("application/problem+json")
        problem = Problem.model_validate(response.json())  # extra="forbid": no undocumented keys
        assert problem.status == code
    assert Problem.model_validate(invalid.json()).errors
