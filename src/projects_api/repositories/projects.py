"""DynamoDB single-table repository for projects.

Key design (partitioned by project id):

    PK                    SK            purpose
    PROJECT#<projectId>   META          the project record
    NAME#<nameKey>        RESERVATION   global, case-insensitive name uniqueness

GSI1 (GSI1PK = OWNER#<ownerId>, GSI1SK = PROJECT#<createdAt>#<projectId>) supports
listing a caller's projects in creation order.
"""

from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from projects_api.config import Settings
from projects_api.domain.exceptions import (
    InvalidCursorError,
    ProjectNameTakenError,
    ProjectNotFoundError,
)
from projects_api.domain.models import Project
from projects_api.domain.validation import name_key
from projects_api.observability import logger

_BOTO_CONFIG = Config(retries={"mode": "adaptive", "max_attempts": 5})


def project_pk(project_id: str) -> str:
    return f"PROJECT#{project_id}"


def name_pk(name: str) -> str:
    return f"NAME#{name_key(name)}"


def owner_gsi1pk(owner_id: str) -> str:
    return f"OWNER#{owner_id}"


GSI1_NAME = "GSI1"
PROJECT_GSI1SK_PREFIX = "PROJECT#"


class ProjectRepository:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._table = settings.table_name
        self._client = client or boto3.client(
            "dynamodb",
            region_name=settings.aws_region,
            endpoint_url=settings.dynamodb_endpoint,
            config=_BOTO_CONFIG,
        )

    # -- writes --------------------------------------------------------------

    def create(self, project: Project) -> Project:
        """Atomically write the project and its name reservation.

        Raises ProjectNameTakenError if another project already holds the name.
        """
        created_at = project.created_at.isoformat()
        project_item = {
            "PK": {"S": project_pk(project.project_id)},
            "SK": {"S": "META"},
            "entity": {"S": "PROJECT"},
            "projectId": {"S": project.project_id},
            "name": {"S": project.name},
            "nameKey": {"S": name_key(project.name)},
            "type": {"S": project.type.value},
            "status": {"S": project.status.value},
            "ownerId": {"S": project.owner_id},
            "createdAt": {"S": created_at},
            "updatedAt": {"S": project.updated_at.isoformat()},
            "GSI1PK": {"S": owner_gsi1pk(project.owner_id)},
            "GSI1SK": {"S": f"{PROJECT_GSI1SK_PREFIX}{created_at}#{project.project_id}"},
        }
        reservation_item = {
            "PK": {"S": name_pk(project.name)},
            "SK": {"S": "RESERVATION"},
            "entity": {"S": "NAME_RESERVATION"},
            "projectId": {"S": project.project_id},
            "ownerId": {"S": project.owner_id},
            "createdAt": {"S": created_at},
        }
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self._table,
                            "Item": reservation_item,
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                    {
                        "Put": {
                            "TableName": self._table,
                            "Item": project_item,
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                ]
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
                reasons = exc.response.get("CancellationReasons", [])
                # Index 0 is the name reservation. A conditional failure there means the
                # name is taken. Any other cancellation is unexpected and re-raised.
                if reasons and reasons[0].get("Code") == "ConditionalCheckFailed":
                    raise ProjectNameTakenError(project.name) from exc
                if not reasons and "ConditionalCheckFailed" in str(exc):
                    raise ProjectNameTakenError(project.name) from exc
            raise
        return project

    def delete(self, project_id: str, owner_id: str) -> None:
        """Delete a project and release its name reservation in one transaction.

        Raises ProjectNotFoundError when the project does not exist or belongs to another
        owner; the caller cannot tell the two apart. The record is read first (consistent)
        to learn the name key, but the deletes are still conditional, so a request that
        loses a race with another delete also ends as ProjectNotFoundError. A reservation
        that no longer points at this project is an invariant violation: it is logged and
        the error propagates rather than reporting success.
        """
        project = self.get(project_id)
        if project.owner_id != owner_id:
            raise ProjectNotFoundError(project_id)
        record_key = {"PK": {"S": project_pk(project_id)}, "SK": {"S": "META"}}
        reservation_key = {"PK": {"S": name_pk(project.name)}, "SK": {"S": "RESERVATION"}}
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Delete": {
                            "TableName": self._table,
                            "Key": record_key,
                            "ConditionExpression": "attribute_exists(PK) AND ownerId = :owner",
                            "ExpressionAttributeValues": {":owner": {"S": owner_id}},
                        }
                    },
                    {
                        "Delete": {
                            "TableName": self._table,
                            "Key": reservation_key,
                            "ConditionExpression": "projectId = :id",
                            "ExpressionAttributeValues": {":id": {"S": project_id}},
                        }
                    },
                ]
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException":
                codes = [r.get("Code") for r in exc.response.get("CancellationReasons", [])]
                # Index 0 is the record: it vanished or changed owner since the read.
                if codes and codes[0] == "ConditionalCheckFailed":
                    raise ProjectNotFoundError(project_id) from exc
                # Index 1 is the reservation: the record exists but its name is not
                # reserved for it. Never silently succeed; surface it for an operator.
                if len(codes) > 1 and codes[1] == "ConditionalCheckFailed":
                    logger.error(
                        "name reservation does not point at the project being deleted",
                        project_id=project_id,
                        record_key=record_key["PK"]["S"],
                        reservation_key=reservation_key["PK"]["S"],
                    )
            raise

    # -- reads ---------------------------------------------------------------

    def get(self, project_id: str) -> Project:
        response = self._client.get_item(
            TableName=self._table,
            Key={"PK": {"S": project_pk(project_id)}, "SK": {"S": "META"}},
            ConsistentRead=True,
        )
        item = response.get("Item")
        if not item:
            raise ProjectNotFoundError(project_id)
        return _to_project(item)

    def list_by_owner(
        self, owner_id: str, *, limit: int, cursor: dict[str, Any] | None = None
    ) -> tuple[list[Project], dict[str, Any] | None]:
        """Return one page of the owner's projects, newest first, from GSI1.

        `cursor` is the raw `LastEvaluatedKey` from a previous page (already validated as
        belonging to this owner). The returned cursor is None when DynamoDB reports no
        further items; note DynamoDB may return a cursor for a page that turns out to be
        the last one, in which case the next call returns an empty page and None.

        The `begins_with` condition keeps future entity types that share the owner
        partition out of the listing.
        """
        params: dict[str, Any] = {
            "TableName": self._table,
            "IndexName": GSI1_NAME,
            "KeyConditionExpression": "GSI1PK = :pk AND begins_with(GSI1SK, :prefix)",
            "ExpressionAttributeValues": {
                ":pk": {"S": owner_gsi1pk(owner_id)},
                ":prefix": {"S": PROJECT_GSI1SK_PREFIX},
            },
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if cursor is not None:
            params["ExclusiveStartKey"] = cursor
        try:
            response = self._client.query(**params)
        except ClientError as exc:
            # A structurally valid token whose key DynamoDB still rejects (for example a
            # key that does not match the key condition) is a bad cursor, not a bug.
            code = exc.response.get("Error", {}).get("Code")
            if cursor is not None and code == "ValidationException":
                raise InvalidCursorError() from exc
            raise
        items = [_to_project(item) for item in response.get("Items", [])]
        last_key: dict[str, Any] | None = response.get("LastEvaluatedKey")
        return items, last_key


def _to_project(item: dict[str, Any]) -> Project:
    return Project.model_validate(
        {
            "projectId": item["projectId"]["S"],
            "name": item["name"]["S"],
            "type": item["type"]["S"],
            "status": item["status"]["S"],
            "ownerId": item["ownerId"]["S"],
            "createdAt": item["createdAt"]["S"],
            "updatedAt": item["updatedAt"]["S"],
        }
    )
