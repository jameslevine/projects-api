"""OpenAPI document post-processing.

FastAPI generates a good baseline; `build_openapi` makes it match what the service actually
puts on the wire:

* every non-2xx response is `application/problem+json` referencing one `Problem` schema, and
  FastAPI's default 422 (this API answers 400) is removed;
* the `x-api-key` security scheme is declared and applied globally, except to `GET /health`,
  so generated clients send the key;
* operationIds are readable (`createProject`, `getHealth`, ...) instead of FastAPI's
  `create_project_v1_projects_post`;
* request and response examples are attached to `createProject`.

Route logic is untouched: routers only declare the status codes they can return.
"""

import json
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute, iter_route_contexts

from projects_api.api.errors import PROBLEM_CONTENT_TYPE, Problem

API_DESCRIPTION = """Create and manage projects that host agents, MCP servers and web apps.

**Authentication**: send your API key in the `x-api-key` header. API Gateway validates it against
a usage plan; the key's id is the owner of every project you create. Other owners' projects
answer `404`, never `403`.

**Errors**: every non-2xx response is `application/problem+json` (RFC 7807) with the `Problem`
shape below. Validation failures are `400` and carry an `errors` array; `403` and `429` are
produced by the gateway for a missing key or a throttled one. In AWS every problem includes a
`requestId`, also sent as the `X-Request-Id` header.
"""

TAGS: list[dict[str, Any]] = [
    {"name": "projects", "description": "Projects owned by the calling API key."},
    {"name": "health", "description": "Unauthenticated liveness check."},
]

SECURITY_SCHEME = "ApiKeyAuth"
PROBLEM_REF = "#/components/schemas/Problem"

# Operations that must not require the API key.
PUBLIC_OPERATIONS: frozenset[tuple[str, str]] = frozenset({("/health", "get")})

# Route function names whose lowerCamelCase form is not already a readable operationId.
OPERATION_IDS = {"health": "getHealth"}

# Responses the platform produces for secured operations even though no route declares them.
GATEWAY_RESPONSES = {
    "403": "Missing or invalid API key (rejected by API Gateway).",
    "429": "Throttled by the usage plan; retry with back-off.",
}
COMMON_RESPONSES = {"500": "Unexpected error. Quote `requestId` when reporting it."}

_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})
# Components FastAPI emits for its 422 response; dropped once nothing references them.
_FASTAPI_VALIDATION_SCHEMAS = ("HTTPValidationError", "ValidationError")

_EXAMPLE_PROJECT: dict[str, Any] = {
    "projectId": "prj_9f1c2b3a4d5e6f708192a3b4c5d6e7f8",
    "name": "my-first-agent",
    "type": "agent",
    "status": "CREATED",
    "ownerId": "a1b2c3d4e5",
    "createdAt": "2026-01-15T09:30:00Z",
    "updatedAt": "2026-01-15T09:30:00Z",
}


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """Generate the OpenAPI document for `app` and apply the post-processing described above."""
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=TAGS,
        servers=[{"url": "/", "description": "The host this document was served from."}],
    )
    components: dict[str, Any] = schema.setdefault("components", {})
    schemas: dict[str, Any] = components.setdefault("schemas", {})
    _add_problem_schema(schemas)
    components["securitySchemes"] = {
        SECURITY_SCHEME: {
            "type": "apiKey",
            "in": "header",
            "name": "x-api-key",
            "description": "API Gateway API key attached to a usage plan.",
        }
    }
    schema["security"] = [{SECURITY_SCHEME: []}]

    operation_ids = _operation_ids(app)
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in _HTTP_METHODS:
                continue
            operation["operationId"] = operation_ids.get((path, method), operation["operationId"])
            public = (path, method) in PUBLIC_OPERATIONS
            if public:
                operation["security"] = []
            _problem_responses(operation, public=public)

    _add_create_project_examples(schema)
    _drop_unreferenced(schema, _FASTAPI_VALIDATION_SCHEMAS)
    return schema


def _add_problem_schema(schemas: dict[str, Any]) -> None:
    problem = Problem.model_json_schema(ref_template="#/components/schemas/{model}")
    schemas.update(problem.pop("$defs", {}))
    schemas["Problem"] = problem


def _operation_ids(app: FastAPI) -> dict[tuple[str, str], str]:
    """Map (path, method) to a readable operationId derived from the route function name.

    Walks routes the way `get_openapi` does: included routers are not flattened into
    `app.routes`, and the context carries the prefix-aware path.
    """
    ids: dict[tuple[str, str], str] = {}
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        path = context.path_format or route.path_format
        operation_id = (
            route.operation_id or OPERATION_IDS.get(route.name) or _lower_camel(route.name)
        )
        for method in route.methods or ():
            ids[(path, method.lower())] = operation_id
    return ids


def _lower_camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(word.capitalize() for word in rest)


def _problem_responses(operation: dict[str, Any], *, public: bool) -> None:
    """Make every non-2xx response problem+json and drop FastAPI's 422."""
    responses: dict[str, Any] = operation.setdefault("responses", {})
    responses.pop("422", None)
    defaults = COMMON_RESPONSES if public else {**GATEWAY_RESPONSES, **COMMON_RESPONSES}
    for code, description in defaults.items():
        responses.setdefault(code, {"description": description})
    for code, response in responses.items():
        if not code.startswith("2"):
            response["content"] = {PROBLEM_CONTENT_TYPE: {"schema": {"$ref": PROBLEM_REF}}}
    operation["responses"] = dict(sorted(responses.items()))


def _add_create_project_examples(schema: dict[str, Any]) -> None:
    operation = _find_operation(schema, "createProject")
    if operation is None:
        return
    operation["requestBody"]["content"]["application/json"]["example"] = {
        "name": "my-first-agent",
        "type": "agent",
    }
    created = operation["responses"]["201"]
    created["description"] = "Project created. `Location` points at the new resource."
    created["headers"] = {
        "Location": {
            "description": "Path of the created project.",
            "schema": {"type": "string"},
            "example": f"/v1/projects/{_EXAMPLE_PROJECT['projectId']}",
        }
    }
    created["content"]["application/json"]["example"] = _EXAMPLE_PROJECT


def _find_operation(schema: dict[str, Any], operation_id: str) -> dict[str, Any] | None:
    for path_item in schema["paths"].values():
        for method in path_item:
            if method not in _HTTP_METHODS:
                continue
            operation: dict[str, Any] = path_item[method]
            if operation.get("operationId") == operation_id:
                return operation
    return None


def _drop_unreferenced(schema: dict[str, Any], names: tuple[str, ...]) -> None:
    """Remove the named component schemas unless something outside them still references them."""
    schemas = schema["components"]["schemas"]
    removed = {name: schemas.pop(name) for name in names if name in schemas}
    dumped = json.dumps(schema)
    for name, definition in removed.items():
        if f'"#/components/schemas/{name}"' in dumped:
            schemas[name] = definition
