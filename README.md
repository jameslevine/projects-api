# Projects API

An HTTP API for creating **projects** that will host an agent, an MCP server or a web
application. A caller authenticates with a per-user API key, posts a name and a type, and gets
back a project record; names are globally unique (case-insensitive) so they can later become
hostnames. The service is a FastAPI application running on AWS Lambda (arm64) behind an API
Gateway REST API with API keys and usage plans, storing everything in one DynamoDB table, with
all infrastructure defined in Terraform. Today the API creates the record only; provisioning the
hosted resource is a later slice.

## Architecture

```text
Client --(x-api-key)--> API Gateway REST (stage "live": usage plan, throttling, access logs,
                        problem+json gateway responses)
                            | GET /health public ; ANY /{proxy+} requires an API key
                            v
                        Lambda python3.12 arm64: FastAPI + Mangum, Powertools logger/tracer/metrics,
                        X-Ray, alias "live" (rollback = repoint the alias)
                            | least-privilege IAM on one table ARN + its indexes
                            v
                        DynamoDB projects-api-<env>: single table (PK/SK), GSI1 by owner,
                        on-demand billing, PITR, encryption at rest
```

- Caller identity is the API key id (`requestContext.identity.apiKeyId`); it becomes `ownerId`.
- Every non-2xx response is `application/problem+json` (RFC 7807), including errors produced by
  the gateway itself (missing key, throttling).
- A project is two items written in one `TransactWriteItems`: the record `PROJECT#<id>/META` and
  the uniqueness reservation `NAME#<nameKey>/RESERVATION`.

Full write-up: [docs/architecture.md](docs/architecture.md) (Well-Architected mapping, data model,
request flow). Decisions: [docs/adr/](docs/adr/).

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-rest-api-for-api-keys.md) | API Gateway REST API (not HTTP API) for API keys and usage plans |
| [0002](docs/adr/0002-single-table-design.md) | DynamoDB single-table design with generic `PK`/`SK` and GSI1 |
| [0003](docs/adr/0003-global-name-uniqueness.md) | Global, case-insensitive name uniqueness via a reservation item and a transaction |
| [0004](docs/adr/0004-fastapi-mangum-on-lambda.md) | FastAPI + Mangum on a single Lambda function |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) and Python 3.12. On Apple Silicon with an x86 `uv`, create the
  venv with the arm64 interpreter first: `uv venv --python /opt/homebrew/bin/python3.12`, then
  `uv sync`.
- Terraform >= 1.3 (CI pins 1.3.4) and AWS CLI v2, for deployment only.
- Docker, for DynamoDB Local when running the API on your machine.
- `gh` (GitHub CLI), for tickets and pull requests.

## Quick start

```bash
uv sync        # install runtime + dev dependencies into .venv
make lint      # ruff check, ruff format --check, mypy --strict
make test      # unit + integration tests (moto in-memory DynamoDB; no AWS needed)
```

`make help` lists every target. `make cov` runs the tests with a coverage report.

## Run locally

```bash
make local-db     # docker compose up DynamoDB Local (port 8000) and create table projects-local
make run-local    # uvicorn on http://localhost:8080 with ENV=local, hot reload
```

There is no API Gateway locally, so identity comes from an `X-Api-Key-Id` header instead of
`x-api-key`. This fallback only works when `ENV=local`. Interactive docs are served at
`http://localhost:8080/v1/docs` in local mode only.

Health check (public, no identity needed):

```bash
curl -s http://localhost:8080/health
```

```json
{"status": "ok", "version": "0.1.0"}
```

Create a project (201). The `Location` header points at the new resource:

```bash
curl -si -X POST http://localhost:8080/v1/projects \
  -H 'X-Api-Key-Id: demo' \
  -H 'content-type: application/json' \
  -d '{"name": "my-first-agent", "type": "agent"}'
```

```http
HTTP/1.1 201 Created
content-type: application/json
location: /v1/projects/prj_8ead2ca56357488283af38744fe08a65

{
  "projectId": "prj_8ead2ca56357488283af38744fe08a65",
  "name": "my-first-agent",
  "type": "agent",
  "status": "CREATED",
  "ownerId": "demo",
  "createdAt": "2026-09-23T16:18:35Z",
  "updatedAt": "2026-09-23T16:18:35Z"
}
```

Duplicate name (409). Comparison is case-insensitive and ignores repeated whitespace, and it is
global: another owner's project with the same name also conflicts.

```bash
curl -si -X POST http://localhost:8080/v1/projects \
  -H 'X-Api-Key-Id: demo' \
  -H 'content-type: application/json' \
  -d '{"name": "My-First-Agent", "type": "web"}'
```

```http
HTTP/1.1 409 Conflict
content-type: application/problem+json

{
  "type": "https://projects-api.example/problems/project-name-taken",
  "title": "Project name already exists",
  "status": 409,
  "detail": "A project named 'My-First-Agent' already exists.",
  "instance": "/v1/projects"
}
```

Invalid name (400). Validation problems carry an `errors` array with one entry per failing
field:

```bash
curl -si -X POST http://localhost:8080/v1/projects \
  -H 'X-Api-Key-Id: demo' \
  -H 'content-type: application/json' \
  -d '{"name": "a/b", "type": "web"}'
```

```http
HTTP/1.1 400 Bad Request
content-type: application/problem+json

{
  "type": "https://projects-api.example/problems/validation",
  "title": "Invalid request",
  "status": 400,
  "detail": "One or more fields failed validation.",
  "instance": "/v1/projects",
  "errors": [
    {
      "field": "name",
      "message": "Value error, Project name may only contain letters, digits, spaces, hyphens and underscores, and must start and end with a letter or digit."
    }
  ]
}
```

Other 400 cases produce the same shape with a different `errors` entry, for example
`{"field": "type", "message": "Input should be 'agent', 'mcp' or 'web'"}` for an unknown type and
`{"field": "extra", "message": "Extra inputs are not permitted"}` for an unexpected property.

When the service runs in Lambda, every problem response also includes a `requestId` (the API
Gateway request id) and echoes it in an `X-Request-Id` header. Locally the field appears only
if you send an `x-request-id` header yourself.

## API reference

Base URL: `http://localhost:8080` locally, or the `api_url` Terraform output (which includes the
`/live` stage) when deployed. All error responses are `application/problem+json` with the fields
`type`, `title`, `status`, `detail`, `instance` and, in AWS, `requestId`.

| Method | Path | Auth | Request body | Responses |
|---|---|---|---|---|
| `GET` | `/health` | public | none | `200` `{"status": "ok", "version": "<semver>"}` |
| `POST` | `/v1/projects` | API key | `{"name": string, "type": "agent" \| "mcp" \| "web"}`; no other properties | `201` project record + `Location`; `400` validation (`errors[]`); `401` no identity (local only); `403` missing or invalid key (gateway); `409` name taken; `429` throttled (gateway) |
| `GET` | `/v1/projects/{projectId}` | API key | none | `200` project record for the owner; `404` when the id is malformed, unknown or belongs to another key; `401` no identity (local only); `403` missing or invalid key (gateway); `429` throttled (gateway) |
| `GET` | `/v1/projects?limit=&nextToken=` | API key | none | `200` `{"items": [project record, ...], "nextToken": string \| null}`, newest first; `400` `limit` outside 1..100 or invalid `nextToken`; `401` no identity (local only); `403` missing or invalid key (gateway); `429` throttled (gateway) |
| `DELETE` | `/v1/projects/{projectId}` | API key | none | planned (S4), [#25](https://github.com/jameslevine/projects-api/issues/25): `204`, `404` for missing or another owner's project |

Project record fields: `projectId` (`prj_` + 32 hex), `name`, `type`, `status` (`CREATED`,
`PROVISIONING`, `READY` or `FAILED`; always `CREATED` today), `ownerId`, `createdAt`,
`updatedAt` (ISO 8601 UTC, second precision).

Resources owned by another key return `404`, never `403`, so project ids cannot be enumerated.

Pagination: `limit` defaults to 20 (1 to 100). `nextToken` is an opaque, URL-safe cursor scoped to
the calling key; pass it back unchanged to fetch the next page, and stop when it is `null`. A token
may lead to an empty final page. Tokens from another key, or edited ones, return `400`.

### OpenAPI

The OpenAPI 3.1 document is served at `/v1/openapi.json` in every environment (Swagger UI at
`/v1/docs` is local only). Every non-2xx response is declared as `application/problem+json`
referencing the `Problem` schema, and the `ApiKeyAuth` scheme (`x-api-key` header) applies to
all operations except `GET /health`. `tests/integration/test_openapi.py` validates the document.

### Validation rules

All rules live in `src/projects_api/domain/validation.py`; the request model in
`src/projects_api/domain/models.py` delegates to it.

`name`

- Leading and trailing whitespace is trimmed and runs of internal whitespace collapse to one
  space before any check (`normalise_name`). Case is preserved for display.
- Length after normalisation: at least `NAME_MIN_LENGTH = 3` and at most `NAME_MAX_LENGTH = 63`
  characters.
- Pattern `^[A-Za-z0-9](?:[A-Za-z0-9 _-]*[A-Za-z0-9])?$`: letters, digits, spaces, hyphens and
  underscores only, and the name must start and end with a letter or digit so it can later be
  turned into a DNS label.
- Uniqueness key (`name_key`): the normalised name lower-cased. Two names that differ only in
  case or whitespace are the same project name.

`type`

- One of `agent`, `mcp` or `web` (the `ProjectType` enum).

The request model uses `extra="forbid"`: any property other than `name` and `type` is a `400`.

## Build

```bash
make build     # scripts/build_lambda.sh -> build/lambda.zip
```

The script exports the locked runtime dependencies with `uv`, installs `aarch64-manylinux2014`
wheels for Python 3.12 regardless of the host platform, adds `src/projects_api`, and fails if the
`pydantic_core` arm64 native wheel is missing from the zip. `make tf-plan` runs this
automatically.

## Deploy

Everything is Terraform under `infra/terraform/`; the `dev` environment is in
`infra/terraform/envs/dev`. Make targets default to `ENV=dev`.

1. One-off: create the remote state bucket and lock table (local state, run once per account).

   ```bash
   make tf-bootstrap STATE_BUCKET=<globally-unique-bucket-name>
   ```

2. Point the environment at that backend. The example file is committed; the real one is not.

   ```bash
   cp -f infra/terraform/envs/dev/backend.example.hcl infra/terraform/envs/dev/backend.hcl
   # edit backend.hcl: set bucket to the STATE_BUCKET name above
   ```

   Optionally set `alarm_email` in `infra/terraform/envs/dev/dev.tfvars` to receive alarm and
   budget notifications.

3. Initialise, plan and apply. `tf-plan` builds the zip first and saves the plan to `tfplan`;
   `tf-apply` applies exactly that saved plan.

   ```bash
   make tf-init
   make tf-plan
   make tf-apply
   ```

4. Read the outputs. The stage ships with one demo API key so it is usable immediately.

   ```bash
   terraform -chdir=infra/terraform/envs/dev output -raw api_url
   terraform -chdir=infra/terraform/envs/dev output -raw demo_api_key_value
   ```

5. Call the deployed API. In AWS the credential is the `x-api-key` header, validated by API
   Gateway; the key's id becomes the `ownerId`.

   ```bash
   API_URL="$(terraform -chdir=infra/terraform/envs/dev output -raw api_url)"
   API_KEY="$(terraform -chdir=infra/terraform/envs/dev output -raw demo_api_key_value)"

   curl -s "${API_URL}/health"
   curl -si -X POST "${API_URL}/v1/projects" \
     -H "x-api-key: ${API_KEY}" \
     -H 'content-type: application/json' \
     -d '{"name": "my-first-agent", "type": "agent"}'
   ```

   Without a valid key the gateway answers `403` as problem+json before the request reaches
   Lambda. The default usage plan allows 10 requests/second (burst 20) and 10,000 requests per
   month per key; the stage is capped at 50 requests/second (burst 100).

`make tf-fmt tf-validate` checks formatting and validates both `bootstrap` and `envs/dev` without
credentials (CI runs the same). Do not run `terraform apply` or mutating `aws` commands unless you
mean to spend money.

## Onboarding a user

Each user gets their own API key attached to the usage plan. The key **id** is the identity the
API sees as `ownerId`; the key **value** is the secret the user sends as `x-api-key`.

```bash
scripts/create_api_key.sh <label>          # env defaults to dev
scripts/create_api_key.sh alice dev
```

The script reads `usage_plan_id` from the Terraform outputs, creates the key
`projects-api-<env>-<label>` with `aws apigateway create-api-key`, attaches it to the plan and
prints the id and value once. Store the value securely; it can only be recovered later with
`aws apigateway get-api-key --include-value`.

## Smoke test

```bash
make smoke                                   # ENV=dev; reads api_url and demo_api_key_value from Terraform
API_URL=... API_KEY=... tests/smoke/smoke.sh  # or against any stage/key
```

The script checks: `GET /health` without a key is `200`; `POST /v1/projects` without a key is
`403`; a create is `201`; the same name in different case is `409`; `a/b` is `400`. Running it
against a real stage is tracked in [#16](https://github.com/jameslevine/projects-api/issues/16).

## Operations

The on-call runbook is [docs/runbook.md](docs/runbook.md) (deploy, rollback, API key
lifecycle, request tracing, alarm playbooks, PITR restore, cost review). In summary: the
`observability` Terraform module creates a CloudWatch dashboard named `projects-api-<env>`
(API count/4XX/5XX, latency p50/p99, Lambda invocations/errors/throttles, business metrics,
DynamoDB capacity and errors), eight alarms (Lambda errors, throttles and p99 duration; API 5XX,
4XX ratio and p99 latency; DynamoDB system errors and throttle events) fanning out to the SNS topic
`projects-api-<env>-alarms`, and a monthly cost budget; set `alarm_email` to subscribe.
Lambda logs are in `/aws/lambda/projects-api-<env>` and gateway access logs in
`/aws/apigateway/projects-api-<env>/access`, both 14-day retention.

Every response carries an `X-Request-Id` header (the API Gateway request id in AWS, so it also
appears in the gateway access log; a UUID locally) and problem bodies repeat it as `requestId`.
Each request produces one `request completed` log line (`route`, `method`, `status`, `owner_id`,
`duration_ms`, `request_id`; never bodies, query strings or headers) and every log line carries the
id as `correlation_id`. To follow a request in CloudWatch Logs Insights:
`fields @timestamp, message, route, status | filter correlation_id = "<X-Request-Id>"`.

## Project layout

```text
src/projects_api/
  main.py               app factory + Lambda `handler`
  config.py             Settings from env vars (TABLE_NAME, ENV, ...)
  observability.py      Powertools logger/tracer/metrics singletons
  api/deps.py           current_user (apiKeyId), repository dependency
  api/errors.py         RFC 7807 problem+json handlers; map domain errors here
  api/context.py        request id resolution + per-request log line middleware
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

Other files: `Makefile` (all commands), `docker-compose.yml` (DynamoDB Local),
`scripts/` (`build_lambda.sh`, `create_api_key.sh`, `create_local_table.py`, `seed_issues.py`),
`.github/workflows/ci.yml` (ruff, mypy, pytest, zip build, `terraform fmt`/`validate` on every
push to `main` and every PR), `CLAUDE.md` (conventions for humans and agents).

## Tickets and workflow

Work is tracked as GitHub Issues, one milestone per feature slice:
[S0 Foundation](https://github.com/jameslevine/projects-api/milestone/1),
[S1 Create project](https://github.com/jameslevine/projects-api/milestone/2),
[S2 Read projects](https://github.com/jameslevine/projects-api/milestone/3),
[S3 Operate](https://github.com/jameslevine/projects-api/milestone/4),
[S4 Lifecycle](https://github.com/jameslevine/projects-api/milestone/5).
[docs/tickets/README.md](docs/tickets/README.md) explains the board, labels and flow; the seed
files next to it are the history of each issue. The delivery plan is in
[docs/PLAN.md](docs/PLAN.md).

Branches are `ticket/<ID>-<slug>` off `main`, PRs are titled `<ID>: <title>` and close their issue;
run `make lint test` (and `make tf-fmt tf-validate` for infra changes) before pushing. See
[CLAUDE.md](CLAUDE.md) for the full conventions.
