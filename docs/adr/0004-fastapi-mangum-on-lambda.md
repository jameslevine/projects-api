# ADR 0004: FastAPI with Mangum on a single Lambda function

- **Status:** Accepted
- **Date:** 2026-09-23
- **Implemented in:** [`src/projects_api/main.py`](../../src/projects_api/main.py),
  [`src/projects_api/observability.py`](../../src/projects_api/observability.py),
  [`infra/terraform/modules/lambda_api/`](../../infra/terraform/modules/lambda_api/main.tf),
  [`scripts/build_lambda.sh`](../../scripts/build_lambda.sh)

## Context

The API is small (a handful of JSON endpoints under `/v1`) but is expected to grow by slices
(read, list, delete, later provisioning). It must run locally without AWS for fast iteration
and tests, generate an OpenAPI document, validate input strictly, return RFC 7807 problems,
and be cheap when idle. The runtime is Python 3.12 with Pydantic v2.

Four ways to run it were considered:

1. **One Lambda function per route**, each with a hand-written handler (or the Powertools
   `APIGatewayRestResolver`). Finest-grained IAM and scaling, but N deployment units, N cold-start
   pools, N sets of Terraform, no shared ASGI middleware, and no local server without extra
   tooling.
2. **One Lambda function running a FastAPI app through Mangum** (an ASGI-to-Lambda adapter).
   The same `app` object runs under uvicorn locally and in tests; Mangum translates the API
   Gateway REST proxy event to ASGI and back.
3. **Lambda Web Adapter**: run uvicorn inside the function behind an AWS-provided extension that
   proxies HTTP to it. Framework-agnostic, but adds an extension layer, a loopback HTTP hop and
   a second process to the cold start, and the raw API Gateway event is no longer visible to the
   application (the caller's `apiKeyId` would need to be forwarded as a header).
4. **Containers** (ECS Fargate or App Runner) running uvicorn. Standard web deployment with no
   cold starts, but always-on cost, more networking to own, and a different deployment and IAM
   story from the rest of the serverless stack.

## Decision

Run the whole API as **one FastAPI application on one Lambda function, adapted by Mangum**,
behind API Gateway's `ANY /{proxy+}` integration.

- **Entry points.** `app` (ASGI, for uvicorn and `TestClient`) and `handler` (Lambda) both live
  in [`main.py`](../../src/projects_api/main.py). Mangum is configured with `lifespan="off"`
  (no startup hooks are needed) and with `application/problem+json` added to its text MIME
  types so error bodies are returned as text rather than base64.
- **Identity from the raw event.** Mangum exposes the API Gateway event as `scope["aws.event"]`;
  [`api/deps.py`](../../src/projects_api/api/deps.py) reads `requestContext.identity.apiKeyId`
  from it. This is the reason the adapter must preserve the event (option 3 would not).
- **arm64.** The function is `architectures = ["arm64"]` on `python3.12`. The build script
  installs `aarch64-manylinux2014` wheels with `uv pip install --python-platform ... --only-binary :all:`
  regardless of the host, and fails the build if the native `pydantic_core` wheel is missing.
- **Cold starts.** Mitigations in place: a pruned package (`__pycache__`, `*.dist-info`, tests
  removed; `--no-compile`; `PYTHONDONTWRITEBYTECODE=1`), module-level initialisation of the app,
  the Mangum adapter and the Powertools singletons, 512 MB memory (more CPU share during init),
  and a `ColdStart` metric plus X-Ray tracing so the real cost is visible. Provisioned
  concurrency is deliberately not configured until measured.
- **Powertools.** `Logger`, `Tracer` and `Metrics` are singletons in
  [`observability.py`](../../src/projects_api/observability.py); the handler is decorated with
  `inject_lambda_context(log_event=False, clear_state=True)`, `capture_lambda_handler` and
  `log_metrics(capture_cold_start_metric=True)`. The tracer is disabled when `ENV=local`.
- **boto3 is bundled.** The Lambda runtime ships boto3/botocore, but the build keeps the versions
  pinned in `uv.lock` so that the runtime matches the tested versions exactly. The build script
  documents the two lines to remove to shrink the zip if that trade-off changes.
- **Versioned function with a `live` alias.** `publish = true` and an alias give a stable target
  for API Gateway and a rollback path (repoint the alias).

## Consequences

Positive:

- One code path for local, test and production: `TestClient` and uvicorn exercise the same
  `app`; integration tests also drive the real `handler` with a synthetic gateway event.
- Framework features come for free: Pydantic validation with `extra="forbid"`, dependency
  injection for identity and repository, exception handlers for the problem+json contract, and a
  generated OpenAPI document at `/v1/openapi.json`.
- One deployment unit, one IAM role, one alarm set, one alias: the Terraform module is small and
  new routes need no infrastructure change (the `{proxy+}` integration already covers them).
- A single warm pool serves all routes, so a request to a rarely-used route benefits from
  warmth created by common ones.
- arm64 lowers the per-GB-second price and, per AWS, the energy per unit of work.

Negative:

- **Coarse IAM.** Every route runs with the same role. Today the policy is seven DynamoDB actions
  on one table, which is acceptable; a route needing broader permissions would widen them for
  all routes. (Asynchronous work such as the S4 provisioner is planned as a separate function,
  which keeps this boundary.)
- **Cold start includes the framework.** Importing FastAPI, Pydantic, Starlette, Mangum and
  Powertools adds hundreds of milliseconds to a cold start compared with a minimal handler. The
  10 s timeout and 29 s gateway limit are far above this, but p99 latency is affected and is
  alarmed at 2 s.
- **One memory and timeout setting** for all routes; a heavy route would force the setting up
  for the light ones.
- **Adapter dependency.** Mangum is a community project; a breaking change in API Gateway event
  shape or ASGI would need an adapter update. Its surface area in this code base is one object
  in `main.py`, so replacing it is contained.
- **Request-response only.** Streaming responses and WebSockets are not available through this
  integration.
- **Bundled boto3 enlarges the zip** and slightly lengthens cold starts, in exchange for
  reproducible behaviour.

## When to revisit

- **Split into more functions** when routes have materially different permissions, memory needs
  or scaling profiles (for example a route that calls other AWS services), or when the package
  grows so that cold starts for the cheap routes are dominated by dependencies they do not use.
- **Add provisioned concurrency or evaluate Lambda SnapStart** if measured cold-start p99 on the
  deployed stage breaches the latency objective after the smoke and load runs in
  [S1-108](../tickets/S1-108-smoke-deployed-stage.md).
- **Move to Lambda Web Adapter or containers** if the application needs streaming responses,
  long-lived connections, requests longer than the API Gateway limit, or a framework feature
  Mangum cannot adapt; or if a steady, high request rate makes always-on compute cheaper than
  per-invocation pricing.
- **Drop bundled boto3** if package size becomes the dominant cold-start factor and the runtime's
  boto3 version is verified against the test suite.
- **Re-check the arm64 choice** if a required dependency ships no `aarch64` wheel; the build
  fails loudly in that case (`--only-binary :all:`).
