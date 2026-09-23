from fastapi import APIRouter, Response, status

from projects_api.api.deps import CurrentUser, Repository
from projects_api.domain.exceptions import ProjectNotFoundError
from projects_api.domain.models import (
    CreateProjectRequest,
    Project,
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
