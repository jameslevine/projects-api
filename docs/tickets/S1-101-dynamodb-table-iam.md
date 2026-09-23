---
title: "S1-101 DynamoDB single table module and least-privilege Lambda IAM"
labels: type:infra, pillar:security, pillar:reliability, pillar:cost
milestone: S1 Create project
status: done
---
## Description
`modules/dynamodb_table`: on-demand table with `PK`/`SK`, GSI1 (`GSI1PK`/`GSI1SK`, ALL projection), PITR, SSE, optional deletion protection and optional Streams. The Lambda role gets `GetItem/PutItem/UpdateItem/DeleteItem/Query/TransactWriteItems/ConditionCheckItem` on the table ARN and its indexes only.

## Acceptance criteria
- Given the module, then `terraform validate` passes and the test fixture in `tests/conftest.py` mirrors the same key schema.
- Given the IAM policy, then it contains no wildcard actions or resources.

## Definition of Done
Validated in CI.
