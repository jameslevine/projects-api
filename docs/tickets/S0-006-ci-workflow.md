---
title: "S0-006 CI workflow: ruff, mypy, pytest, zip build, terraform fmt/validate"
labels: type:chore, pillar:operations
milestone: S0 Foundation
status: done
---
## Description
GitHub Actions workflow with two jobs: `python` (uv sync, ruff check + format, mypy, pytest with coverage, build zip, upload artefact) and `terraform` (fmt check, validate bootstrap and dev with `-backend=false`).

## Acceptance criteria
- Given a PR, when CI runs, then both jobs must pass before merge.
- Given no AWS credentials in CI, then the workflow still passes (no plan/apply).

## Definition of Done
Workflow green on `main`.
