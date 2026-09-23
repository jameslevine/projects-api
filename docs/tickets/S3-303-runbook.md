---
title: "S3-303 Operations runbook"
labels: type:docs, pillar:operations
milestone: S3 Operate
status: open
---
## Description
Write `docs/runbook.md` for an on-call engineer: service overview and dashboards; deploy procedure (`make build tf-plan tf-apply`); rollback (repoint the `live` Lambda alias; reference `scripts/rollback.sh` from S3-305 as pending if not merged); API key lifecycle (create with `scripts/create_api_key.sh`, disable with `aws apigateway update-api-key --patch-operations op=replace,path=/enabled,value=false`, rotate); how to find a request by `requestId` in Lambda logs and API access logs (Logs Insights queries); alarm playbooks for each alarm in `modules/observability` (what it means, first checks, escalation); DynamoDB PITR restore steps; monthly cost review checklist.

## Acceptance criteria
- Given every alarm resource in `modules/observability/main.tf`, then the runbook has a section with the same alarm name.
- Given the Logs Insights queries, then they reference the actual log group names from the modules.

## Definition of Done
Merged and linked from README.
