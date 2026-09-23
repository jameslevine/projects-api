---
title: "S0-003 Terraform bootstrap: state bucket and lock table"
labels: type:infra, pillar:reliability, pillar:security
milestone: S0 Foundation
status: done
---
## Description
One-off Terraform root in `infra/terraform/bootstrap` that creates a versioned, encrypted, private S3 bucket for remote state and a DynamoDB lock table. `prevent_destroy` on both.

## Acceptance criteria
- Given the root, when I run `terraform init -backend=false && terraform validate`, then it succeeds.
- Given an apply, then the bucket blocks public access, has versioning and SSE enabled, and old versions expire after 90 days.

## Definition of Done
Validated in CI; README documents `make tf-bootstrap STATE_BUCKET=...`.
