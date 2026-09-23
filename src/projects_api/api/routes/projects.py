from fastapi import APIRouter, Response, status

from projects_api.api.deps import CurrentUser, Repository
from projects_api.domain.models import CreateProjectRequest, Project, ProjectResponse
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
