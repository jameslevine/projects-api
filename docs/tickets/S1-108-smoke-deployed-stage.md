---
title: "S1-108 Run the smoke test against a deployed dev stage"
labels: type:test, pillar:operations, status:blocked
milestone: S1 Create project
status: blocked
---
## Description
Deploy `envs/dev` and run `make smoke` (`tests/smoke/smoke.sh`), which checks: `/health` 200 without key, `/v1/projects` 403 without key, 201 create, 409 duplicate, 400 invalid name.

## Acceptance criteria
- Given a deployed stage and the demo key, when `make smoke` runs, then it prints `5 passed, 0 failed`.

## Blocked by
Valid AWS credentials on the deploying machine or an OIDC role for GitHub Actions. Unblock by fixing credentials, running `make tf-bootstrap STATE_BUCKET=<name>`, creating `infra/terraform/envs/dev/backend.hcl`, then `make tf-init tf-plan tf-apply smoke`.

## Definition of Done
Smoke output pasted into this issue.
