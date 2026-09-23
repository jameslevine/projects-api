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
from projects_api.domain.exceptions import ProjectNameTakenError, ProjectNotFoundError
from projects_api.domain.models import Project
from projects_api.domain.validation import name_key

_BOTO_CONFIG = Config(retries={"mode": "adaptive", "max_attempts": 5})


def project_pk(project_id: str) -> str:
    return f"PROJECT#{project_id}"


def name_pk(name: str) -> str:
    return f"NAME#{name_key(name)}"


def owner_gsi1pk(owner_id: str) -> str:
    return f"OWNER#{owner_id}"


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
            "GSI1SK": {"S": f"PROJECT#{created_at}#{project.project_id}"},
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
