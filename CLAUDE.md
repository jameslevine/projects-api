# Projects API: conventions for humans and agents

Read this before changing anything. The plan is in `docs/PLAN.md`; tickets are GitHub Issues
(seeded from `docs/tickets/*.md`).

## Stack

- Python 3.12, FastAPI, Mangum (Lambda adapter), Pydantic v2, boto3, AWS Lambda Powertools.
- AWS: API Gateway REST API (API keys + usage plans), Lambda arm64, DynamoDB single table.
- Terraform >= 1.3, AWS provider ~> 5.0. Region eu-west-2.
- Tooling: `uv` (deps and venv), `ruff` (lint/format), `mypy --strict`, `pytest` + `moto`.

## Commands

| Task | Command |
|---|---|
| Install | `uv sync` (on this Mac the venv must be arm64: `uv venv --python /opt/homebrew/bin/python3.12` first) |
| Lint + types | `make lint` |
| Tests | `make test` |
| Terraform | `make tf-fmt tf-validate` (no credentials needed; provider start-up is slow, allow several minutes) |
| Build zip | `make build` |
| Local API | `make local-db && make run-local`, then send `X-Api-Key-Id: <id>` as identity |

Never run `terraform apply`, mutating `aws` commands, or anything that costs money unless told to.

## Layout

```text
src/projects_api/
  main.py               app factory + Lambda `handler`
  config.py             Settings from env vars (TABLE_NAME, ENV, ...)
  observability.py      Powertools logger/tracer/metrics singletons
  api/deps.py           current_user (apiKeyId), repository dependency
  api/errors.py         RFC 7807 problem+json handlers; map domain errors here
  api/openapi.py        OpenAPI post-processing (Problem schema, security scheme, examples)
  api/routes/*.py       one router per resource, prefix /v1
  domain/validation.py  the ONLY place validation rules live
  domain/models.py      Pydantic models (camelCase aliases on the wire)
  domain/exceptions.py  *Error classes raised by repositories/services
  repositories/*.py     DynamoDB access via boto3 client; no HTTP concepts
tests/unit, tests/integration (TestClient + moto), tests/smoke (deployed stage)
infra/terraform/{bootstrap,modules/*,envs/*}
docs/{PLAN.md,architecture.md,adr/,runbook.md,tickets/}
```

## Rules

- **Errors**: raise a domain exception; register its mapping in `api/errors.py`. Every non-2xx is
  `application/problem+json`. Never leak stack traces.
- **Identity**: the owner is `requestContext.identity.apiKeyId`. Other owners' resources return 404,
  never 403 (no enumeration).
- **DynamoDB**: single table, keys `PK`/`SK`, GSI1 for owner queries. New entity types get a
  `PK` prefix (`PROJECT#`, `NAME#`, ...). Atomic multi-item writes use `TransactWriteItems`.
  Always use `ConditionExpression`s; never read-then-write.
- **Validation**: Pydantic models with `extra="forbid"`. Rules live in `domain/validation.py`.
- **Logging**: Powertools `logger` with structured kwargs. Never log request bodies or key values.
- **Terraform**: one module per AWS concern, typed and described variables, tags via
  `default_tags`, least-privilege IAM (specific actions, specific ARNs). Must pass
  `terraform fmt -check` and `terraform validate`. Avoid features newer than Terraform 1.3.
- **Tests**: every behaviour change has a test. Integration tests use the `dynamodb_table`
  fixture in `tests/conftest.py`. Deterministic: no network, no sleeps.
- **Docs**: decisions go in `docs/adr/NNNN-title.md` (Status, Context, Decision, Consequences,
  date). Update `README.md` when commands or endpoints change.
- **Shell**: this machine aliases `cp` to `cp -iv`; in scripts and one-liners use `cp -f` or
  redirects so nothing prompts.

## Git and GitHub workflow

- Branch from `main`: `ticket/<ID>-<short-slug>` (for example `ticket/S2-201-get-project`).
- Commit messages: imperative mood, one logical change per commit, reference the issue (`#12`).
- Before pushing: `make lint test`; if infra changed also `make tf-fmt tf-validate`.
- Open a PR with `gh pr create`. Title `<ID>: <title>`. Body: what/why, how tested, and a line
  `Closes #<issue>`. Never push to `main` directly. PRs are squash-merged by the orchestrator.
- Comment on the issue when you start (`Started`) and when the PR is open (`PR: <url>`).
- Do not modify files outside your ticket's scope; if you must, say so in the PR body.
