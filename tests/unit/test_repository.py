from typing import Any

import pytest

from projects_api.config import Settings
from projects_api.domain.exceptions import ProjectNameTakenError, ProjectNotFoundError
from projects_api.domain.models import Project, ProjectType
from projects_api.repositories.projects import ProjectRepository, name_pk, project_pk
from tests.conftest import TABLE_NAME


@pytest.fixture
def repo(dynamodb_table: Any) -> ProjectRepository:
    return ProjectRepository(Settings(table_name=TABLE_NAME), client=dynamodb_table)


def test_create_writes_project_and_reservation(
    repo: ProjectRepository, dynamodb_table: Any
) -> None:
    project = Project.new(name="Demo App", type_=ProjectType.WEB, owner_id="key-1")
    repo.create(project)

    meta = dynamodb_table.get_item(
        TableName=TABLE_NAME, Key={"PK": {"S": project_pk(project.project_id)}, "SK": {"S": "META"}}
    )["Item"]
    assert meta["name"]["S"] == "Demo App"
    assert meta["nameKey"]["S"] == "demo app"
    assert meta["GSI1PK"]["S"] == "OWNER#key-1"

    reservation = dynamodb_table.get_item(
        TableName=TABLE_NAME, Key={"PK": {"S": name_pk("demo app")}, "SK": {"S": "RESERVATION"}}
    )["Item"]
    assert reservation["projectId"]["S"] == project.project_id


def test_create_is_rejected_when_name_taken_case_insensitively(repo: ProjectRepository) -> None:
    repo.create(Project.new(name="Demo App", type_=ProjectType.WEB, owner_id="key-1"))
    with pytest.raises(ProjectNameTakenError):
        repo.create(Project.new(name="  demo   APP ", type_=ProjectType.AGENT, owner_id="key-2"))


def test_failed_create_leaves_no_partial_write(
    repo: ProjectRepository, dynamodb_table: Any
) -> None:
    repo.create(Project.new(name="taken", type_=ProjectType.WEB, owner_id="key-1"))
    second = Project.new(name="TAKEN", type_=ProjectType.WEB, owner_id="key-2")
    with pytest.raises(ProjectNameTakenError):
        repo.create(second)
    resp = dynamodb_table.get_item(
        TableName=TABLE_NAME, Key={"PK": {"S": project_pk(second.project_id)}, "SK": {"S": "META"}}
    )
    assert "Item" not in resp


def test_get_round_trips(repo: ProjectRepository) -> None:
    project = Project.new(name="round trip", type_=ProjectType.MCP, owner_id="key-1")
    repo.create(project)
    assert repo.get(project.project_id) == project


def test_get_missing_raises(repo: ProjectRepository) -> None:
    with pytest.raises(ProjectNotFoundError):
        repo.get("prj_missing")
