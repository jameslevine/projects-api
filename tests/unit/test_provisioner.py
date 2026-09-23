"""Provisioner handler against a moto table, driven by synthetic DynamoDB Streams events.

The stream images are the same DynamoDB JSON that `ProjectRepository.create` writes, so the
events look exactly like what the table stream would deliver for a new project.
"""

from typing import Any

import pytest
from botocore.exceptions import ClientError

from projects_api.domain.models import ProjectStatus, ProjectType
from projects_api.repositories.projects import project_pk
from projects_provisioner import handler as provisioner
from projects_provisioner.handler import ProjectStatusStore
from projects_provisioner.provisioners import (
    PROVISIONERS,
    ProvisionRequest,
    ProvisionResult,
)
from tests.conftest import TABLE_NAME

OLD_TIMESTAMP = "2026-01-01T00:00:00+00:00"
STREAM_ARN = "arn:aws:dynamodb:eu-west-2:123456789012:table/projects-test/stream/2026-01-01"


class _Ctx:
    aws_request_id = "req-prov-1"
    function_name = "projects-api-test-provisioner"
    memory_limit_in_mb = 512
    invoked_function_arn = (
        "arn:aws:lambda:eu-west-2:123456789012:function:projects-api-test-provisioner"
    )


def project_item(
    project_id: str, *, status: str = "CREATED", type_: str = "web", owner: str = "key-1"
) -> dict[str, Any]:
    return {
        "PK": {"S": project_pk(project_id)},
        "SK": {"S": "META"},
        "entity": {"S": "PROJECT"},
        "projectId": {"S": project_id},
        "name": {"S": f"Project {project_id[-4:]}"},
        "nameKey": {"S": f"project {project_id[-4:]}"},
        "type": {"S": type_},
        "status": {"S": status},
        "ownerId": {"S": owner},
        "createdAt": {"S": OLD_TIMESTAMP},
        "updatedAt": {"S": OLD_TIMESTAMP},
        "GSI1PK": {"S": f"OWNER#{owner}"},
        "GSI1SK": {"S": f"PROJECT#{OLD_TIMESTAMP}#{project_id}"},
    }


def reservation_item(project_id: str) -> dict[str, Any]:
    return {
        "PK": {"S": "NAME#some name"},
        "SK": {"S": "RESERVATION"},
        "entity": {"S": "NAME_RESERVATION"},
        "projectId": {"S": project_id},
        "ownerId": {"S": "key-1"},
        "createdAt": {"S": OLD_TIMESTAMP},
    }


def stream_record(
    image: dict[str, Any] | None, *, event_name: str = "INSERT", sequence: str
) -> dict[str, Any]:
    dynamodb: dict[str, Any] = {
        "ApproximateCreationDateTime": 1767225600,
        "SequenceNumber": sequence,
        "SizeBytes": 256,
        "StreamViewType": "NEW_AND_OLD_IMAGES",
    }
    if image is not None:
        dynamodb["Keys"] = {"PK": image["PK"], "SK": image["SK"]}
        dynamodb["NewImage"] = image
    return {
        "eventID": f"evt-{sequence}",
        "eventName": event_name,
        "eventVersion": "1.1",
        "eventSource": "aws:dynamodb",
        "awsRegion": "eu-west-2",
        "dynamodb": dynamodb,
        "eventSourceARN": STREAM_ARN,
    }


def stream_event(*records: dict[str, Any]) -> dict[str, Any]:
    return {"Records": list(records)}


def put(client: Any, item: dict[str, Any]) -> None:
    client.put_item(TableName=TABLE_NAME, Item=item)


def get(client: Any, project_id: str) -> dict[str, Any]:
    response = client.get_item(
        TableName=TABLE_NAME,
        Key={"PK": {"S": project_pk(project_id)}, "SK": {"S": "META"}},
        ConsistentRead=True,
    )
    item: dict[str, Any] = response["Item"]
    return item


@pytest.fixture
def client(dynamodb_table: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """The moto client, with the handler's store pointed at the moto table."""
    monkeypatch.setattr(provisioner, "_store", ProjectStatusStore(TABLE_NAME, dynamodb_table))
    return dynamodb_table


PID_A = "prj_" + "a" * 32
PID_B = "prj_" + "b" * 32


def test_created_project_becomes_ready_with_updated_timestamp(client: Any) -> None:
    put(client, project_item(PID_A))

    response = provisioner.handler(
        stream_event(stream_record(project_item(PID_A), sequence="1")), _Ctx()
    )

    assert response == {"batchItemFailures": []}
    after = get(client, PID_A)
    assert after["status"]["S"] == ProjectStatus.READY
    assert after["updatedAt"]["S"] != OLD_TIMESTAMP
    assert after["createdAt"]["S"] == OLD_TIMESTAMP
    assert "failureReason" not in after
    assert "endpoint" not in after  # the stubs return no endpoint


def test_every_project_type_is_provisioned(client: Any) -> None:
    assert set(PROVISIONERS) == set(ProjectType)
    records = []
    for index, project_type in enumerate(ProjectType):
        pid = f"prj_{index:032d}"
        put(client, project_item(pid, type_=project_type.value))
        records.append(
            stream_record(project_item(pid, type_=project_type.value), sequence=str(index))
        )

    response = provisioner.handler(stream_event(*records), _Ctx())

    assert response == {"batchItemFailures": []}
    for index in range(len(ProjectType)):
        assert get(client, f"prj_{index:032d}")["status"]["S"] == ProjectStatus.READY


def test_already_ready_record_is_not_written(client: Any) -> None:
    put(client, project_item(PID_A, status="READY"))
    before = get(client, PID_A)

    # 1. The stream image itself says READY (for example a replayed later record).
    response = provisioner.handler(
        stream_event(stream_record(project_item(PID_A, status="READY"), sequence="1")), _Ctx()
    )
    assert response == {"batchItemFailures": []}
    assert get(client, PID_A) == before

    # 2. The image says CREATED but the table has moved on: the conditional write must not fire.
    response = provisioner.handler(
        stream_event(stream_record(project_item(PID_A), sequence="2")), _Ctx()
    )
    assert response == {"batchItemFailures": []}
    assert get(client, PID_A) == before


class _Boom:
    def provision(self, project: ProvisionRequest) -> ProvisionResult:
        raise RuntimeError("upstream exploded: " + "x" * 600)


def test_provisioner_failure_marks_failed_and_does_not_raise(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(PROVISIONERS, ProjectType.WEB, _Boom())
    put(client, project_item(PID_A, type_="web"))

    response = provisioner.handler(
        stream_event(stream_record(project_item(PID_A), sequence="1")), _Ctx()
    )

    assert response == {"batchItemFailures": []}, "a terminal failure must not be retried"
    after = get(client, PID_A)
    assert after["status"]["S"] == ProjectStatus.FAILED
    assert after["failureReason"]["S"].startswith("upstream exploded: ")
    assert len(after["failureReason"]["S"]) == 500
    assert after["updatedAt"]["S"] != OLD_TIMESTAMP


class _Endpoint:
    def provision(self, project: ProvisionRequest) -> ProvisionResult:
        return ProvisionResult(
            endpoint=f"https://{project.project_id}.example.test", details={"a": "b"}
        )


def test_endpoint_is_stored_when_the_provisioner_returns_one(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(PROVISIONERS, ProjectType.MCP, _Endpoint())
    put(client, project_item(PID_A, type_="mcp"))

    provisioner.handler(
        stream_event(stream_record(project_item(PID_A, type_="mcp"), sequence="1")), _Ctx()
    )

    after = get(client, PID_A)
    assert after["status"]["S"] == ProjectStatus.READY
    assert after["endpoint"]["S"] == f"https://{PID_A}.example.test"


class _FailingUpdates:
    """Delegates to the moto client but fails `update_item` for one project."""

    def __init__(self, client: Any, failing_pk: str) -> None:
        self._client = client
        self._failing_pk = failing_pk

    def update_item(self, **kwargs: Any) -> Any:
        if kwargs["Key"]["PK"]["S"] == self._failing_pk:
            raise ClientError(
                {"Error": {"Code": "InternalServerError", "Message": "DynamoDB is unhappy"}},
                "UpdateItem",
            )
        return self._client.update_item(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def test_dynamodb_error_reports_only_that_record_as_failed(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        provisioner,
        "_store",
        ProjectStatusStore(TABLE_NAME, _FailingUpdates(client, project_pk(PID_B))),
    )
    put(client, project_item(PID_A))
    put(client, project_item(PID_B))

    response = provisioner.handler(
        stream_event(
            stream_record(project_item(PID_A), sequence="11"),
            stream_record(project_item(PID_B), sequence="22"),
        ),
        _Ctx(),
    )

    assert response == {"batchItemFailures": [{"itemIdentifier": "22"}]}
    assert get(client, PID_A)["status"]["S"] == ProjectStatus.READY
    assert get(client, PID_B)["status"]["S"] == ProjectStatus.CREATED, "left for the retry"


def test_non_project_non_insert_and_imageless_records_are_skipped(client: Any) -> None:
    put(client, project_item(PID_A))
    before = get(client, PID_A)

    response = provisioner.handler(
        stream_event(
            stream_record(reservation_item(PID_A), sequence="1"),
            stream_record(project_item(PID_A), event_name="MODIFY", sequence="2"),
            stream_record(None, event_name="REMOVE", sequence="3"),
        ),
        _Ctx(),
    )

    assert response == {"batchItemFailures": []}
    assert get(client, PID_A) == before


def test_stub_provisioners_succeed_without_side_effects() -> None:
    request = ProvisionRequest(project_id=PID_A, name="n", type=ProjectType.AGENT, owner_id="k")
    for project_type, impl in PROVISIONERS.items():
        result = impl.provision(ProvisionRequest(**{**request.__dict__, "type": project_type}))
        assert result == ProvisionResult(endpoint=None, details={})
