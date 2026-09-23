---
title: "S3-301 Business metrics and alarm review: ProjectNameConflicts, API p99 latency alarm"
labels: type:feature, type:infra, pillar:operations, pillar:reliability
milestone: S3 Operate
status: open
---
## Description
Emit a Powertools metric `ProjectNameConflicts` (Count) when a 409 is returned (in the `ProjectNameTakenError` handler in `api/errors.py`), and add it to the business widget in `modules/observability`. Add an API Gateway `Latency` p99 alarm (variable threshold, default 1500 ms, 3 of 3 periods). Review every alarm in `modules/observability/main.tf` against the AWS metric documentation: namespace, metric name, dimensions (`ApiName`+`Stage`, `FunctionName`, `TableName`), statistic. Fix anything wrong and note it in the PR.

## Acceptance criteria
- Given a 409 response through the Lambda handler path, then the flushed EMF metrics include `ProjectNameConflicts` = 1 (capture stdout in the test).
- Given `terraform validate`, then it passes; the dashboard JSON includes the new metric.

## Definition of Done
Tests + `make tf-fmt tf-validate` green.
