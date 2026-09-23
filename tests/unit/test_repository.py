from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from projects_api.config import Settings
from projects_api.domain.exceptions import (
    InvalidCursorError,
    ProjectNameTakenError,
    ProjectNotFoundError,
)
from projects_api.domain.models import Project, ProjectStatus, ProjectType
from projects_api.repositories.projects import (
    ProjectRepository,
    name_pk,
    owner_gsi1pk,
    project_pk,
)
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


# -- list_by_owner ----------------------------------------------------------------


_T0 = datetime(2026, 9, 23, 10, 0, 0, tzinfo=UTC)


def _project_at(owner_id: str, seconds: int, name: str | None = None) -> Project:
    """A project with an explicit createdAt so ordering is deterministic."""
    at = _T0 + timedelta(seconds=seconds)
    return Project(
        project_id=f"prj_{uuid4().hex}",
        name=name or f"{owner_id} {seconds}",
        type=ProjectType.WEB,
        status=ProjectStatus.CREATED,
        owner_id=owner_id,
        created_at=at,
        updated_at=at,
    )


def _seed(repo: ProjectRepository, owner_id: str, count: int) -> list[Project]:
    """Create `count` projects one second apart and return them newest first."""
    projects = [_project_at(owner_id, i) for i in range(count)]
    for project in projects:
        repo.create(project)
    return list(reversed(projects))


def test_list_by_owner_returns_newest_first(repo: ProjectRepository) -> None:
    expected = _seed(repo, "key-1", 3)
    items, cursor = repo.list_by_owner("key-1", limit=10)
    assert items == expected
    assert cursor is None


def test_list_by_owner_honours_limit_and_continues_from_cursor(repo: ProjectRepository) -> None:
    expected = _seed(repo, "key-1", 5)

    page1, cursor1 = repo.list_by_owner("key-1", limit=2)
    assert page1 == expected[:2]
    assert cursor1 is not None
    assert set(cursor1) == {"PK", "SK", "GSI1PK", "GSI1SK"}
    assert cursor1["GSI1PK"] == {"S": owner_gsi1pk("key-1")}

    page2, cursor2 = repo.list_by_owner("key-1", limit=2, cursor=cursor1)
    assert page2 == expected[2:4]
    assert cursor2 is not None

    page3, cursor3 = repo.list_by_owner("key-1", limit=2, cursor=cursor2)
    assert page3 == expected[4:]
    assert cursor3 is None


def test_list_by_owner_never_includes_other_owners(repo: ProjectRepository) -> None:
    mine = _seed(repo, "key-1", 3)
    theirs = _seed(repo, "key-2", 2)
    seen: list[Project] = []
    cursor: dict[str, Any] | None = None
    for _ in range(10):
        items, cursor = repo.list_by_owner("key-1", limit=1, cursor=cursor)
        seen.extend(items)
        if cursor is None:
            break
    assert seen == mine
    assert not {p.project_id for p in seen} & {p.project_id for p in theirs}


def test_list_by_owner_for_unknown_owner_is_empty(repo: ProjectRepository) -> None:
    _seed(repo, "key-1", 1)
    assert repo.list_by_owner("key-nobody", limit=10) == ([], None)


def test_list_by_owner_ignores_other_entities_in_the_owner_partition(
    repo: ProjectRepository, dynamodb_table: Any
) -> None:
    expected = _seed(repo, "key-1", 2)
    # A hypothetical future entity type sharing GSI1PK must not leak into the listing.
    dynamodb_table.put_item(
        TableName=TABLE_NAME,
        Item={
            "PK": {"S": "DEPLOYMENT#dep_1"},
            "SK": {"S": "META"},
            "entity": {"S": "DEPLOYMENT"},
            "GSI1PK": {"S": owner_gsi1pk("key-1")},
            "GSI1SK": {"S": "ZZZ#9999#dep_1"},
        },
    )
    items, cursor = repo.list_by_owner("key-1", limit=10)
    assert items == expected
    assert cursor is None


class _RejectingClient:
    """Stands in for DynamoDB refusing an ExclusiveStartKey it does not like."""

    def query(self, **_: Any) -> dict[str, Any]:
        raise ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Exclusive Start Key invalid"}},
            "Query",
        )


class _ThrottlingClient:
    def query(self, **_: Any) -> dict[str, Any]:
        raise ClientError(
            {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow"}},
            "Query",
        )


def test_list_by_owner_maps_rejected_start_key_to_invalid_cursor() -> None:
    repo = ProjectRepository(Settings(table_name=TABLE_NAME), client=_RejectingClient())
    with pytest.raises(InvalidCursorError):
        repo.list_by_owner("key-1", limit=5, cursor={"PK": {"S": "x"}})


def test_list_by_owner_reraises_validation_error_without_cursor() -> None:
    repo = ProjectRepository(Settings(table_name=TABLE_NAME), client=_RejectingClient())
    with pytest.raises(ClientError):
        repo.list_by_owner("key-1", limit=5)


def test_list_by_owner_reraises_other_client_errors_with_cursor() -> None:
    repo = ProjectRepository(Settings(table_name=TABLE_NAME), client=_ThrottlingClient())
    with pytest.raises(ClientError):
        repo.list_by_owner("key-1", limit=5, cursor={"PK": {"S": "x"}})
