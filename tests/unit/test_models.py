import pytest
from pydantic import ValidationError

from projects_api.domain.models import (
    CreateProjectRequest,
    Project,
    ProjectStatus,
    ProjectType,
)


def test_create_request_accepts_valid_payload() -> None:
    req = CreateProjectRequest.model_validate({"name": " demo app ", "type": "web"})
    assert req.name == "demo app"
    assert req.type is ProjectType.WEB


def test_create_request_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        CreateProjectRequest.model_validate({"name": "demo", "type": "database"})


def test_create_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CreateProjectRequest.model_validate({"name": "demo", "type": "web", "owner": "x"})


def test_new_project_defaults() -> None:
    p = Project.new(name="demo", type_=ProjectType.AGENT, owner_id="key-1")
    assert p.project_id.startswith("prj_")
    assert p.status is ProjectStatus.CREATED
    assert p.created_at == p.updated_at
    assert p.created_at.tzinfo is not None


def test_project_serialises_camel_case() -> None:
    p = Project.new(name="demo", type_=ProjectType.MCP, owner_id="key-1")
    body = p.model_dump(by_alias=True, mode="json")
    assert set(body) == {"projectId", "name", "type", "status", "ownerId", "createdAt", "updatedAt"}
