---
title: "S4-402 Provisioning pipeline skeleton: DynamoDB Streams to provisioner Lambda with status transitions"
labels: type:feature, type:infra, pillar:reliability, pillar:operations
milestone: S4 Lifecycle
status: open
---
## Description
Enable Streams on the table (`stream_enabled=true`, NEW_AND_OLD_IMAGES). New Terraform module `modules/lambda_provisioner`: python3.12 arm64 function subscribed to the stream with an event-source-mapping filter for `INSERT` where `entity = PROJECT`, batch size 10, bisect on error, max retry 3, on-failure destination SQS DLQ, and an alarm on DLQ depth. New package `src/projects_provisioner/` with a handler that, per record, performs a conditional `UpdateItem` `CREATED -> PROVISIONING`, calls a `Provisioner` protocol keyed by `ProjectType` (stub implementations that return success), then `PROVISIONING -> READY` (or `FAILED` with `failureReason`). Idempotent: skip records whose status is not `CREATED`. Reuse `Settings`, `observability` and key helpers from `projects_api`; do not duplicate.

## Acceptance criteria
- Given a synthetic stream INSERT record for a `CREATED` project, when the handler runs against moto, then the item ends `READY` with `updatedAt` changed.
- Given a record for a project already `READY`, then no write happens.
- Given a stub provisioner that raises, then the item ends `FAILED` with `failureReason` and the handler does not raise (so the batch is not retried forever).
- Given `terraform validate` for dev, then it passes with the new module wired.

## Dependencies
None on other S4 tickets. Touches `modules/dynamodb_table` (already has `stream_enabled`), `envs/dev/main.tf`, new module and package, `scripts/build_lambda.sh` (package both handlers in one zip or produce a second zip).

## Definition of Done
Tests + `make lint test tf-fmt tf-validate` green; architecture doc updated with the async flow.
