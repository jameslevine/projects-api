"""Provisioner Lambda entry point: DynamoDB Streams records -> project status transitions.

The event source mapping (infra/terraform/modules/lambda_provisioner) delivers batches of
stream records, pre-filtered to `INSERT` of items whose `entity` is `PROJECT`. For each new
project still in status `CREATED` the handler:

1. moves it `CREATED -> PROVISIONING` with a conditional `UpdateItem` (a failed condition means
   another invocation already handled this record: skip, which makes replays idempotent);
2. runs the `Provisioner` registered for the project's type;
3. moves it `PROVISIONING -> READY` (storing `endpoint` when the provisioner returns one), or
   `PROVISIONING -> FAILED` with `failureReason` when the provisioner raised.

Failure semantics differ on purpose:

* a provisioner exception is terminal for that project: it is recorded as `FAILED` and the
  record counts as processed, so the batch is not retried for something a retry cannot fix;
* DynamoDB/boto errors propagate, so Powertools reports the record in `batchItemFailures` and
  the event source mapping retries it (bisecting the batch, then the DLQ after the retry limit).

Known gap: if the write that records FAILED itself fails, the project stays PROVISIONING (the
replayed record is skipped by the condition). A reconciler for stuck PROVISIONING items is a
follow-up.
"""

from datetime import UTC, datetime
from typing import Any

import boto3
from aws_lambda_powertools.utilities.batch import (
    BatchProcessor,
    EventType,
    process_partial_response,
)
from aws_lambda_powertools.utilities.batch.types import PartialItemFailureResponse
from aws_lambda_powertools.utilities.data_classes.dynamo_db_stream_event import DynamoDBRecord
from aws_lambda_powertools.utilities.typing import LambdaContext
from boto3.dynamodb.types import TypeDeserializer
from botocore.config import Config
from botocore.exceptions import ClientError

from projects_api.config import get_settings
from projects_api.domain.models import ProjectStatus, ProjectType
from projects_api.observability import logger, metrics, tracer
from projects_api.repositories.projects import project_pk
from projects_provisioner.provisioners import PROVISIONERS, ProvisionRequest, ProvisionResult

PROJECT_ENTITY = "PROJECT"
MAX_FAILURE_REASON_LENGTH = 500

processor = BatchProcessor(event_type=EventType.DynamoDBStreams)
_deserializer = TypeDeserializer()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class ProjectStatusStore:
    """The conditional status transitions the provisioner performs on project records.

    Every write carries a `ConditionExpression` on the current status, so a record is never
    moved twice and a stale replay never overwrites a later state.
    """

    def __init__(self, table_name: str, client: Any) -> None:
        self._table = table_name
        self._client = client

    def begin(self, project_id: str) -> bool:
        """CREATED -> PROVISIONING. False if the record is no longer CREATED."""
        return self._transition(
            project_id, expected=ProjectStatus.CREATED, target=ProjectStatus.PROVISIONING
        )

    def complete(self, project_id: str, result: ProvisionResult) -> bool:
        """PROVISIONING -> READY, storing the endpoint when there is one."""
        extra = {"endpoint": {"S": result.endpoint}} if result.endpoint else {}
        return self._transition(
            project_id, expected=ProjectStatus.PROVISIONING, target=ProjectStatus.READY, extra=extra
        )

    def fail(self, project_id: str, reason: str) -> bool:
        """PROVISIONING -> FAILED with a bounded `failureReason`."""
        extra = {"failureReason": {"S": reason[:MAX_FAILURE_REASON_LENGTH] or "unknown error"}}
        return self._transition(
            project_id,
            expected=ProjectStatus.PROVISIONING,
            target=ProjectStatus.FAILED,
            extra=extra,
        )

    def _transition(
        self,
        project_id: str,
        *,
        expected: ProjectStatus,
        target: ProjectStatus,
        extra: dict[str, Any] | None = None,
    ) -> bool:
        names = {"#s": "status", "#u": "updatedAt"}
        values: dict[str, Any] = {
            ":expected": {"S": expected.value},
            ":target": {"S": target.value},
            ":now": {"S": _now()},
        }
        assignments = ["#s = :target", "#u = :now"]
        for index, (attribute, value) in enumerate(sorted((extra or {}).items())):
            names[f"#x{index}"] = attribute
            values[f":x{index}"] = value
            assignments.append(f"#x{index} = :x{index}")
        try:
            self._client.update_item(
                TableName=self._table,
                Key={"PK": {"S": project_pk(project_id)}, "SK": {"S": "META"}},
                UpdateExpression="SET " + ", ".join(assignments),
                ConditionExpression="#s = :expected",
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise
        return True


_store: ProjectStatusStore | None = None


def _get_store() -> ProjectStatusStore:
    """One store (and one boto3 client) per execution environment; tests inject their own."""
    global _store
    if _store is None:
        settings = get_settings()
        client = boto3.client(
            "dynamodb",
            region_name=settings.aws_region,
            endpoint_url=settings.dynamodb_endpoint,
            config=Config(retries={"mode": "adaptive", "max_attempts": 5}),
        )
        _store = ProjectStatusStore(settings.table_name, client)
    return _store


def record_handler(record: DynamoDBRecord) -> None:
    """Process one stream record. Raising marks the record failed for the batch response."""
    raw = record.raw_event
    event_name = raw.get("eventName")
    if event_name != "INSERT":
        logger.debug("skipping record", reason="not an INSERT", event_name=event_name)
        return
    new_image = raw.get("dynamodb", {}).get("NewImage")
    if not new_image:
        logger.debug("skipping record", reason="no NewImage")
        return
    image: dict[str, Any] = _deserializer.deserialize({"M": new_image})
    if image.get("entity") != PROJECT_ENTITY:
        logger.debug("skipping record", reason="not a project", entity=image.get("entity"))
        return
    if image.get("status") != ProjectStatus.CREATED:
        logger.debug("skipping record", reason="not CREATED", status=image.get("status"))
        return

    project_id = str(image["projectId"])
    project_type = ProjectType(str(image["type"]))
    store = _get_store()
    if not store.begin(project_id):
        logger.info("project already handled; skipping", project_id=project_id)
        return

    request = ProvisionRequest(
        project_id=project_id,
        name=str(image["name"]),
        type=project_type,
        owner_id=str(image["ownerId"]),
    )
    try:
        result = PROVISIONERS[project_type].provision(request)
    except Exception as exc:
        # Terminal for this project: record FAILED and count the record as processed.
        logger.exception("provisioning failed", project_id=project_id, type=project_type.value)
        metrics.add_metric(name="ProjectsProvisioningFailed", unit="Count", value=1)
        if not store.fail(project_id, str(exc)):
            logger.warning(
                "status changed during provisioning; FAILED not recorded", project_id=project_id
            )
        return

    if store.complete(project_id, result):
        metrics.add_metric(name="ProjectsProvisioned", unit="Count", value=1)
        logger.info(
            "project provisioned",
            project_id=project_id,
            type=project_type.value,
            endpoint=result.endpoint,
            details=result.details,
        )
    else:
        logger.warning(
            "status changed during provisioning; READY not recorded", project_id=project_id
        )


@logger.inject_lambda_context(log_event=False, clear_state=True)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict[str, Any], context: LambdaContext) -> PartialItemFailureResponse:
    return process_partial_response(
        event=event, record_handler=record_handler, processor=processor, context=context
    )
