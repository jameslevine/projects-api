# Projects API platform: GitHub Issues + agent-driven delivery

## Context

Greenfield build in `/Users/james/Coding/schroders-test`: an AWS-hosted API (API Gateway REST + FastAPI on Lambda + DynamoDB single table, all Terraform) that lets a user create a "project" to host an agent, an MCP server or a web app, designed against the five Well-Architected pillars and shipped in feature slices.

**Status at the point of re-planning.** Slices 0 and 1 are largely implemented locally and passing: 45 tests, ruff and mypy clean, Terraform bootstrap validated. Not yet done: dev-env `terraform validate` and the Lambda zip build (both interrupted), docs/ADRs/README/runbook, CLAUDE.md, git commit, GitHub repo, tickets.

**Change of direction (this revision).** Tickets move from Markdown files to **GitHub Issues created with `gh`**, and **subagents pick up and complete the tickets** via branch + PR, which I (the orchestrator) verify and merge. All slices including S4 are in scope. Up to 3 agents run in parallel, one slice at a time.

Decisions confirmed with the user (earlier + this revision):

- Auth: API key per user via API Gateway usage plans; caller identity = `requestContext.identity.apiKeyId`. REST API (HTTP APIs do not support keys).
- Validation: user-chosen name, 3 to 63 chars, letters/digits/space/hyphen/underscore, alphanumeric at both ends; 201 on create, 409 if taken (global, case-insensitive).
- "Create" stores the record only; provisioning is S4.
- Tickets: GitHub Issues, one milestone per slice, labels for type/pillar/slice.
- Workflow: branch + PR per ticket, orchestrator merges after checks pass (squash, delete branch).
- Scope: everything through S4. Parallelism: up to 3 agents, one slice at a time.
- Repo: **`jameslevine/projects-api`, public.**

Assumptions (flagged): python3.12 arm64 Lambda; region eu-west-2; Terraform pinned `>= 1.3`, AWS provider `~> 5.0`. AWS credentials on this machine are invalid, so nothing is deployed in this session; GitHub Actions CI runs lint, tests, zip build and `terraform validate` on every PR. `terraform` and `uv` are x86 binaries under Rosetta: provider start-up is slow (allow 5 to 10 minutes for validate), and the venv must use the arm64 Homebrew Python 3.12 (`uv venv --python /opt/homebrew/bin/python3.12`).

## Architecture (unchanged, for reference)

```
Client --(x-api-key)--> API Gateway REST (stage live, usage plan, throttling, access logs, problem+json gateway responses)
                            | {proxy+} ANY api_key_required ; GET /health public
                            v
                      Lambda python3.12 arm64: FastAPI + Mangum, Powertools logger/tracer/metrics, X-Ray, alias "live"
                            | least-privilege IAM on one table ARN + indexes
                            v
                      DynamoDB projects-{env}: PK/SK single table, GSI1 by owner, on-demand, PITR
```

Items: `PROJECT#<id>` / `META` (record) and `NAME#<nameKey>` / `RESERVATION` (uniqueness), written in one `TransactWriteItems`. Code lives in `src/projects_api/` (`domain/validation.py` is the single source of validation rules, `repositories/projects.py` the table access, `api/errors.py` the RFC 7807 handlers, `api/deps.py` the identity dependency). Infra in `infra/terraform/{bootstrap,modules/*,envs/dev}`.

## Orchestrator setup (done by me, before any agent starts)

1. **Finish verification of existing work**: `terraform validate` in `infra/terraform/envs/dev` (long timeout), `scripts/build_lambda.sh` (expect arm64 `pydantic_core` `.so` in the zip), `make lint test`.
2. **Write `CLAUDE.md`** (repo conventions agents must follow): stack, commands (`make lint test tf-validate build`), layout, validation/error conventions, branch naming `ticket/<id>-<slug>`, commit style, PR body must contain `Closes #<n>`, never touch `main` directly, run `make lint test` before pushing, Terraform must pass `fmt -check` and `validate`, no AWS applies.
3. **Git + GitHub**: rename branch to `main`, initial commit, `gh repo create jameslevine/projects-api --public --source=. --remote=origin --push`. Because the repo is public, double-check nothing sensitive is committed (no `.env`, no tfvars with emails, no state files; `.gitignore` already excludes these). Enable squash merge and auto-delete branches (`gh repo edit --enable-squash-merge --delete-branch-on-merge`).
4. **Labels and milestones** via `gh label create` / `gh api repos/:owner/:repo/milestones`: labels `type:feature|infra|docs|test|chore`, `pillar:security|reliability|performance|cost|operations`, `slice:S0..S4`, `status:blocked`; milestones `S0 Foundation`, `S1 Create project`, `S2 Read projects`, `S3 Operate`, `S4 Lifecycle`.
5. **Seed issues** with `scripts/seed_issues.sh`, which reads `docs/tickets/*.md` (one file per ticket: title line, labels/milestone metadata, body with description, acceptance criteria as Given/When/Then, dependencies, Definition of Done) and calls `gh issue create --title --body-file --label --milestone`. Idempotent: skips titles that already exist. Tickets already implemented in the initial commit are closed immediately with a comment `Implemented in <sha>`.
6. **Board**: `docs/tickets/README.md` links to the milestones and explains the flow. Optionally a GitHub Project board (`gh project create`) with the milestone view; the `project` scope is available.

## Tickets

Ticket body template: Description, Acceptance criteria (Given/When/Then), Dependencies, Definition of Done (code + tests + docs updated + `make lint test` green + CI green + PR merged).

**S0 Foundation** (milestone `S0 Foundation`). Usable output: deployed, monitored `GET /health`.
- S0-001 Repo scaffold: uv, ruff, mypy, pytest, Makefile, .gitignore. *done*
- S0-002 FastAPI skeleton, `/health`, Mangum handler, Powertools, problem+json. *done*
- S0-003 Terraform bootstrap (state bucket, lock table). *done, validated*
- S0-004 `lambda_api` + `api_gateway_rest` modules, `envs/dev`. *done, validate pending*
- S0-005 Lambda arm64 build script. *done, build pending*
- S0-006 CI workflow (ruff, mypy, pytest, zip build, tf fmt/validate). *done, first run on push*
- S0-007 `docs/architecture.md` with pillar mapping + ADR 0001 (REST API for API keys) + ADR 0004 (FastAPI/Mangum on Lambda). **agent**
- S0-008 `CLAUDE.md` + `docs/tickets/README.md` + `scripts/seed_issues.sh`. *orchestrator*

**S1 Create project** (milestone `S1 Create project`). Usable output: key holder creates a project, gets 201 or 409.
- S1-101 `dynamodb_table` module + least-privilege IAM. *done*
- S1-102 Domain model + validation rules + unit tests. *done*
- S1-103 Repository with transactional name reservation + moto tests. *done*
- S1-104 `POST /v1/projects` + 400/409 problem+json + integration tests. *done*
- S1-105 API key identity, usage plan, demo key, gateway responses, `scripts/create_api_key.sh`. *done*
- S1-106 Local dev loop: docker-compose DynamoDB Local, `scripts/create_local_table.py`, `make run-local`. *done*
- S1-107 `README.md` quick start (local, test, build, deploy, smoke) + ADR 0002 (single table) + ADR 0003 (global name uniqueness). **agent**
- S1-108 Smoke test verified against a deployed stage. *blocked: AWS credentials* (`status:blocked`)

**S2 Read projects** (milestone `S2 Read projects`). Usable output: owners list and fetch their projects.
- S2-201 `GET /v1/projects/{projectId}`: 200 for owner, 404 for missing or other owner; tests. **agent A**
- S2-202 `GET /v1/projects`: owner query on GSI1, cursor pagination (`limit` 1..100, opaque base64 `nextToken`), `Query` with `ScanIndexForward=false`; tests. **agent A (same files as 201, sequential)**
- S2-203 OpenAPI polish: response examples, problem schema component, `/v1/openapi.json` served through the gateway, contract test that the schema is valid. **agent B**

**S3 Operate** (milestone `S3 Operate`). Usable output: on-call sees health and gets paged.
- S3-301 Emit `ProjectNameConflicts` metric on 409 and add to dashboard; verify all alarm metric names/dimensions against AWS docs; latency alarm on API p99. **agent A**
- S3-302 Correlation: Powertools `correlation_id_path=API_GATEWAY_REST`, log owner id and route on every request, `X-Request-Id` echoes the gateway request id. **agent B**
- S3-303 `docs/runbook.md`: deploy, rollback via alias, key issue/rotate/disable, read logs by request id, alarm playbooks, cost review. **agent C**
- S3-304 Optional WAF WebACL (AWS managed rule groups) behind a `enable_waf` variable; tflint + checkov jobs in CI. **agent A (after 301)**
- S3-305 `scripts/rollback.sh` repointing the `live` alias to a previous version; documented. **agent B (after 302)**

**S4 Lifecycle** (milestone `S4 Lifecycle`). Usable output: delete works, provisioning pipeline skeleton exists, prod env defined.
- S4-401 `DELETE /v1/projects/{projectId}`: transactional delete of record + reservation, 204, 404 for other owners; tests. **agent A**
- S4-402 DynamoDB Streams enabled (`stream_enabled`), `provisioner` Lambda (new module `lambda_provisioner`, filtered on INSERT of `entity=PROJECT`) moving status `CREATED -> PROVISIONING -> READY|FAILED` via conditional update, DLQ + alarm; tests with synthetic stream events. **agent B**
- S4-403 ADR 0005: per-type provisioning design (agent / mcp / web), what resources each type gets, trust boundaries, cost model. **agent C**
- S4-404 `infra/terraform/envs/prod`: separate state key, stricter throttles, deletion protection on, budget higher, `alarm_email` required; CI validates both envs. **agent C (after 403)**

## Agent execution protocol

For each slice, in order S0 remainder+S1 remainder, S2, S3, S4:

1. Orchestrator spawns up to 3 `general-purpose` agents with `isolation: "worktree"`, each prompt containing: the issue number and full body (`gh issue view <n>`), the repo conventions (CLAUDE.md), the exact files they own, files they must not touch, the commands to run (`make lint test`, `make tf-fmt tf-validate` when infra changes), and the finish steps: commit on `ticket/<id>-<slug>`, `git push -u origin`, `gh pr create --title "<id>: <title>" --body "...Closes #<n>"`, `gh issue edit <n> --add-assignee @me` is skipped (agents are not GitHub users); instead they comment `Started by agent` / `PR opened: <url>`.
2. Tickets that touch the same files (S2-201/202, S3-301/304, S3-302/305, S4-403/404) go to one agent sequentially to avoid merge conflicts.
3. Orchestrator waits for agent completion notices, then per PR: `gh pr checks <n> --watch`, read the diff, pull the branch and run `make lint test` locally, `gh pr merge <n> --squash --delete-branch`. If checks fail or the diff is wrong, `SendMessage` the same agent with the failure and ask it to fix and push.
4. After the slice is merged: `git pull`, rerun `make lint test` on `main`, close the milestone, start the next slice.
5. Blocked tickets (S1-108 smoke against a real deployment) stay open with `status:blocked` and a comment explaining what unblocks them.

## Verification

- Local: `make lint` (ruff, ruff format, mypy) and `make test` (45+ tests, growing per slice) green on `main` after every slice merge.
- Infra: `make tf-validate` for bootstrap and dev (and prod after S4-404); `scripts/build_lambda.sh` produces `build/lambda.zip` with aarch64 wheels.
- GitHub: CI green on every PR (`gh pr checks`); every issue closed by a merged PR (`gh issue list --state closed --milestone ...`); `gh issue list --state open` shows only `status:blocked` items at the end.
- Deployment and smoke (`make tf-bootstrap`, `make tf-plan`, `make tf-apply`, `make smoke`) cannot run here because AWS credentials are invalid, and will be reported as not verified.
