from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from projects_api.api.deps import CurrentUser, Repository
from projects_api.api.pagination import decode_cursor, encode_cursor
from projects_api.domain.exceptions import ProjectNotFoundError
from projects_api.domain.models import (
    CreateProjectRequest,
    Project,
    ProjectListResponse,
    ProjectResponse,
    is_valid_project_id,
)
from projects_api.observability import logger, metrics

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectResponse,
    response_model_by_alias=True,
    summary="Create a project",
    responses={
        400: {"description": "Validation failed (problem+json)."},
        409: {"description": "A project with this name already exists (problem+json)."},
    },
)
def create_project(
    body: CreateProjectRequest, owner_id: CurrentUser, repo: Repository, response: Response
) -> Project:
    """Create a project that will host an agent, an MCP server or a web application.

    Names are globally unique and compared case-insensitively.
    """
    project = Project.new(name=body.name, type_=body.type, owner_id=owner_id)
    repo.create(project)
    metrics.add_metric(name="ProjectsCreated", unit="Count", value=1)
    logger.info("project created", project_id=project.project_id, type=project.type.value)
    response.headers["Location"] = f"/v1/projects/{project.project_id}"
    return project


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@router.get(
    "",
    response_model=ProjectListResponse,
    response_model_by_alias=True,
    summary="List the caller's projects",
    responses={
        400: {"description": "`limit` out of range or `nextToken` invalid (problem+json)."},
    },
)
def list_projects(
    owner_id: CurrentUser,
    repo: Repository,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description=f"Page size, 1 to {MAX_PAGE_SIZE}. Defaults to {DEFAULT_PAGE_SIZE}.",
        ),
    ] = DEFAULT_PAGE_SIZE,
    next_token: Annotated[
        str | None,
        Query(
            alias="nextToken",
            description="Opaque cursor from the previous page's `nextToken`.",
        ),
    ] = None,
) -> ProjectListResponse:
    """List the caller's projects, newest first, one page at a time.

    Only the caller's own projects are ever returned. A `nextToken` minted for another
    caller is rejected as invalid.
    """
    cursor = decode_cursor(next_token, owner_id) if next_token is not None else None
    projects, last_key = repo.list_by_owner(owner_id, limit=limit, cursor=cursor)
    logger.debug("projects listed", count=len(projects), has_more=last_key is not None)
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p, from_attributes=True) for p in projects],
        next_token=encode_cursor(last_key) if last_key is not None else None,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    response_model_by_alias=True,
    summary="Get a project",
    responses={
        404: {"description": "No project with this id belongs to the caller (problem+json)."},
    },
)
def get_project(project_id: str, owner_id: CurrentUser, repo: Repository) -> Project:
    """Return one of the caller's projects.

    A malformed id, an unknown id and another owner's id all produce the same 404 so
    that project ids cannot be enumerated or probed.
    """
    if not is_valid_project_id(project_id):
        raise ProjectNotFoundError(project_id)
    project = repo.get(project_id)
    if project.owner_id != owner_id:
        raise ProjectNotFoundError(project_id)
    return project


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a project",
    responses={
        404: {"description": "No project with this id belongs to the caller (problem+json)."},
    },
)
def delete_project(project_id: str, owner_id: CurrentUser, repo: Repository) -> Response:
    """Delete one of the caller's projects and release its name for reuse.

    The record and its name reservation go in one transaction. A malformed id, an unknown
    id and another owner's id all produce the same 404, and nothing is removed.
    """
    if not is_valid_project_id(project_id):
        raise ProjectNotFoundError(project_id)
    repo.delete(project_id, owner_id)
    metrics.add_metric(name="ProjectsDeleted", unit="Count", value=1)
    logger.info("project deleted", project_id=project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
