---
title: "S0-007 Architecture document with Well-Architected mapping, ADR 0001 and ADR 0004"
labels: type:docs, pillar:operations
milestone: S0 Foundation
status: open
---
## Description
Write `docs/architecture.md`: component diagram (Mermaid), request flow, data model (single table, item types, GSI1), error model, identity model, and a section per Well-Architected pillar (security, reliability, performance efficiency, cost optimisation, operational excellence, sustainability) mapping concrete choices in this repo to the pillar, with pointers to the Terraform module or Python file that implements each.

Write two ADRs in `docs/adr/` using the format Status / Context / Decision / Consequences with a date:
- `0001-rest-api-for-api-keys.md`: why API Gateway REST API rather than HTTP API (API keys + usage plans), trade-offs (cost, latency, features), what would make us revisit.
- `0004-fastapi-mangum-on-lambda.md`: why FastAPI + Mangum on a single Lambda (vs one Lambda per route, vs Lambda Web Adapter, vs containers), cold-start considerations, arm64, Powertools.

## Acceptance criteria
- Given `docs/architecture.md`, then every pillar section names at least three concrete implementation choices with file references that exist in the repo.
- Given the ADRs, then each has Status, Context, Decision, Consequences and a date.
- Given the Mermaid diagram, then it renders on GitHub.

## Dependencies
None. Read `docs/PLAN.md`, `src/projects_api/`, `infra/terraform/` for facts; do not describe features that are not implemented.

## Definition of Done
Files merged and linked from README (add a "Docs" section if missing).
