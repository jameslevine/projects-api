import pytest
from pydantic import ValidationError

from projects_api.domain.models import (
    PROJECT_ID_PATTERN,
    CreateProjectRequest,
    Project,
    ProjectStatus,
    ProjectType,
    is_valid_project_id,
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


def test_generated_project_ids_satisfy_the_id_pattern() -> None:
    for _ in range(20):
        p = Project.new(name="demo", type_=ProjectType.WEB, owner_id="key-1")
        assert is_valid_project_id(p.project_id), p.project_id
        assert PROJECT_ID_PATTERN.fullmatch(p.project_id)


@pytest.mark.parametrize(
    "value",
    [
        "prj_doesnotexist",
        "prj_",
        "prj_" + "0" * 31,
        "prj_" + "0" * 33,
        "prj_" + "g" * 32,
        "prj_" + "A" * 32,
        "PRJ_" + "0" * 32,
        " prj_" + "0" * 32,
        "prj_" + "0" * 32 + "\n",
        "0" * 32,
        "",
    ],
)
def test_is_valid_project_id_rejects_malformed_values(value: str) -> None:
    assert not is_valid_project_id(value)
