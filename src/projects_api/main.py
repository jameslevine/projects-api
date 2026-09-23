"""Application entry point.

`app` is the FastAPI ASGI application (run locally with uvicorn).
`handler` is the AWS Lambda entry point, adapting API Gateway REST events via Mangum.
"""

from typing import Any

from fastapi import FastAPI
from mangum import Mangum
from mangum.adapter import DEFAULT_TEXT_MIME_TYPES

from projects_api import __version__
from projects_api.api.errors import register_error_handlers
from projects_api.api.openapi import API_DESCRIPTION, build_openapi
from projects_api.api.routes import health, projects
from projects_api.config import get_settings
from projects_api.observability import logger, metrics, tracer


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Projects API",
        version=__version__,
        description=API_DESCRIPTION,
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs" if settings.is_local else None,
        redoc_url=None,
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(projects.router)

    def custom_openapi() -> dict[str, Any]:
        """Serve the post-processed OpenAPI document, generated once and cached on the app."""
        if app.openapi_schema is None:
            app.openapi_schema = build_openapi(app)
        return app.openapi_schema

    # The override pattern FastAPI documents; mypy objects only to assigning a method.
    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app


app = create_app()

_mangum = Mangum(
    app,
    lifespan="off",
    # problem+json is text; without this Mangum would base64-encode error bodies.
    text_mime_types=[*DEFAULT_TEXT_MIME_TYPES, "application/problem+json"],
)


@logger.inject_lambda_context(log_event=False, clear_state=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return _mangum(event, context)
