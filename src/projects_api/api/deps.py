"""FastAPI dependencies: caller identity, settings and repository."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from projects_api.config import Settings, get_settings
from projects_api.repositories.projects import ProjectRepository

LOCAL_IDENTITY_HEADER = "x-api-key-id"


def current_user(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> str:
    """Resolve the caller's identity.

    In AWS, API Gateway has already validated the `x-api-key` header against a usage
    plan and puts the key's id on `requestContext.identity.apiKeyId`. Mangum exposes the
    raw event as `scope["aws.event"]`. That id is the owner identity.

    Locally (ENV=local) there is no gateway, so an `X-Api-Key-Id` header stands in.
    This fallback is disabled outside local to avoid header spoofing.
    """
    event = request.scope.get("aws.event")
    if event:
        api_key_id = event.get("requestContext", {}).get("identity", {}).get("apiKeyId")
        if api_key_id:
            return str(api_key_id)
    if settings.is_local:
        header = request.headers.get(LOCAL_IDENTITY_HEADER)
        if header:
            return header
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing caller identity.")


@lru_cache(maxsize=1)
def _repository() -> ProjectRepository:
    """One repository (and one boto3 client) per Lambda execution environment."""
    return ProjectRepository(get_settings())


def get_repository() -> ProjectRepository:
    return _repository()


CurrentUser = Annotated[str, Depends(current_user)]
Repository = Annotated[ProjectRepository, Depends(get_repository)]
