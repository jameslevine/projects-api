"""RFC 7807 problem+json error handling.

All non-2xx responses share one shape so clients can handle them uniformly:

    {"type": "...", "title": "...", "status": 409, "detail": "...", "instance": "/v1/projects",
     "requestId": "..."}
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from projects_api.domain.exceptions import (
    InvalidCursorError,
    ProjectNameTakenError,
    ProjectNotFoundError,
)
from projects_api.observability import logger

PROBLEM_CONTENT_TYPE = "application/problem+json"
_TYPE_BASE = "https://projects-api.example/problems/"


def request_id(request: Request) -> str | None:
    ctx = request.scope.get("aws.context")
    if ctx is not None:
        return str(getattr(ctx, "aws_request_id", None) or "")
    return request.headers.get("x-request-id")


def problem(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str,
    problem_type: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": _TYPE_BASE + problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
    }
    rid = request_id(request)
    if rid:
        body["requestId"] = rid
    if extra:
        body.update(extra)
    headers = {"X-Request-Id": rid} if rid else None
    return JSONResponse(
        body, status_code=status_code, media_type=PROBLEM_CONTENT_TYPE, headers=headers
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(p) for p in e.get("loc", []) if p != "body"),
                "message": e.get("msg", ""),
            }
            for e in exc.errors()
        ]
        return problem(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Invalid request",
            detail="One or more fields failed validation.",
            problem_type="validation",
            extra={"errors": errors},
        )

    @app.exception_handler(InvalidCursorError)
    async def _invalid_cursor(request: Request, exc: InvalidCursorError) -> JSONResponse:
        return problem(
            request,
            status_code=status.HTTP_400_BAD_REQUEST,
            title="Invalid request",
            detail=str(exc),
            problem_type="invalid-cursor",
        )

    @app.exception_handler(ProjectNameTakenError)
    async def _name_taken(request: Request, exc: ProjectNameTakenError) -> JSONResponse:
        return problem(
            request,
            status_code=status.HTTP_409_CONFLICT,
            title="Project name already exists",
            detail=str(exc),
            problem_type="project-name-taken",
        )

    @app.exception_handler(ProjectNotFoundError)
    async def _not_found(request: Request, exc: ProjectNotFoundError) -> JSONResponse:
        return problem(
            request,
            status_code=status.HTTP_404_NOT_FOUND,
            title="Project not found",
            detail=str(exc),
            problem_type="project-not-found",
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(
            request,
            status_code=exc.status_code,
            title=_TITLES.get(exc.status_code, "Error"),
            detail=str(exc.detail),
            problem_type=f"http-{exc.status_code}",
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return problem(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal server error",
            detail="An unexpected error occurred. Quote the requestId when reporting it.",
            problem_type="internal",
        )


_TITLES = {
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    405: "Method not allowed",
    409: "Conflict",
    413: "Payload too large",
    415: "Unsupported media type",
    429: "Too many requests",
}
