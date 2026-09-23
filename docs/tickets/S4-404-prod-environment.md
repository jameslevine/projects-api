---
title: "S4-404 Production environment"
labels: type:infra, pillar:reliability, pillar:security, pillar:cost
milestone: S4 Lifecycle
status: open
---
## Description
Create `infra/terraform/envs/prod` mirroring dev with: separate state key (`projects-api/prod/terraform.tfstate`), `deletion_protection=true`, Lambda `reserved_concurrency` cap, stricter stage and per-key throttles, `alarm_email` required (variable validation), `monthly_budget_usd` higher, WAF enabled if S3-304 is merged, lower `POWERTOOLS_LOGGER_SAMPLE_RATE`. Refactor shared wiring into a `modules/stack` module if dev and prod would otherwise duplicate more than about 30 lines, and make dev use it too. Add prod to the CI terraform job and to the Makefile (`ENV=prod`).

## Acceptance criteria
- Given both envs, then `terraform validate` passes and `terraform fmt -check` passes.
- Given `alarm_email` unset for prod, then validation fails with a clear message.

## Dependencies
After S4-403 (sequential on the same agent; rebase on `main` first to pick up S3-304 and S4-402 changes).

## Definition of Done
CI validates dev and prod; README deploy section mentions `ENV=prod`.
