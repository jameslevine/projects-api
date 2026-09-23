# ADR 0001: API Gateway REST API, chosen for API keys and usage plans

- **Status:** Accepted
- **Date:** 2026-09-23
- **Implemented in:** [`infra/terraform/modules/api_gateway_rest/`](../../infra/terraform/modules/api_gateway_rest/main.tf),
  [`src/projects_api/api/deps.py`](../../src/projects_api/api/deps.py),
  [`scripts/create_api_key.sh`](../../scripts/create_api_key.sh)

## Context

The service needs to identify each caller so that projects have an owner, and it needs to
limit how much each caller may do. The agreed authentication model (see
[docs/PLAN.md](../PLAN.md)) is one API key per user, issued by an operator, with per-key
throttling and a monthly quota. There is no user directory, no sign-up flow and no browser
client at this stage, so an OAuth or OIDC provider would be infrastructure without a consumer.

Amazon API Gateway offers two HTTP front doors for Lambda:

- **HTTP API** (API Gateway v2): lower price per million requests (roughly a third of the REST
  API price), lower added latency, JWT and Lambda authorizers, simpler configuration. It does
  **not** support API keys, usage plans, per-key throttling or quotas, request validators, or
  customised gateway responses.
- **REST API** (API Gateway v1): supports API keys and usage plans (`x-api-key` validation,
  per-key rate/burst/quota, `requestContext.identity.apiKeyId` on the event), request
  validators, gateway response templates, WAF association, resource policies, caching and
  canary deployments. It costs more per request and adds a few more milliseconds of overhead.

Doing key management in application code on top of an HTTP API was considered: it would need a
key store, hashing, a lookup on every request, our own throttling and quota accounting, and a
rotation flow. All of that already exists in REST API usage plans.

## Decision

Use an **API Gateway REST API** with a **regional** endpoint and a single stage `live`.

- `ANY /{proxy+}` requires an API key; `GET /health` does not.
- One default **usage plan** (10 requests/s, burst 20, 10,000 requests/month per key) plus
  stage-level throttling (50 requests/s, burst 100). Every user key is attached to this plan by
  [`scripts/create_api_key.sh`](../../scripts/create_api_key.sh); Terraform creates one `demo` key.
- The **key id** (`requestContext.identity.apiKeyId`) is the owner identity used by the
  application. The key value is never handled by application code.
- Gateway responses for `UNAUTHORIZED`, `INVALID_API_KEY` and `THROTTLED` are rewritten as
  `application/problem+json`, so the error contract holds even when Lambda is not invoked.
- A request validator checks path parameters at the gateway; body validation stays in
  FastAPI/Pydantic so the rules live in one place.

## Consequences

Positive:

- Per-user identity, throttling and quotas with no application code and no secret storage on
  our side; keys can be disabled or rotated with a single API Gateway call.
- Bad or missing keys and throttled requests are rejected before Lambda runs, which protects
  cost and the table during abuse.
- The gateway can present the same RFC 7807 error shape as the application.
- WAF, caching and canary deployments are available later without changing the front door
  (WAF is planned in [S3-304](../tickets/S3-304-waf-and-security-scanning.md)).
- API access logs include `apiKeyId`, giving per-owner traceability for free.

Negative:

- Higher per-request cost than HTTP API. At the expected volumes (a quota of 10,000 requests per
  key per month) the difference is small in absolute terms, but it grows linearly with traffic.
- Slightly higher latency per request than HTTP API.
- More Terraform: resources, methods, integrations, a deployment with an explicit redeploy
  trigger, method settings, an account-level CloudWatch role and gateway responses, compared
  with a handful of resources for an HTTP API.
- API keys are a shared secret sent on every request. They identify a key, not a person, and
  carry no claims (roles, tenants), so authorisation is limited to "owner of the key".
- API Gateway limits the number of keys per account and region; the design assumes tens to
  low thousands of users, not millions.
- Because the gateway returns 403 for a missing key (`INVALID_API_KEY`), the API cannot
  distinguish "no credentials" (401) from "bad credentials" at the edge.

## When to revisit

Move to an **HTTP API with a JWT authorizer (Amazon Cognito or another OIDC provider)** when
any of the following holds:

- Users need to sign up or sign in themselves, or a browser or mobile client appears, so
  short-lived tokens and claims (roles, tenant, scopes) are needed rather than a static key.
- Per-request cost or latency becomes a material fraction of the bill or the SLO, and usage
  plans are no longer the mechanism that enforces fairness (for example, quotas move to the
  application or to WAF rate rules).
- Keys need to carry more than identity (fine-grained authorisation), or the account-level key
  limit is approached.

Reconsider staying on REST but changing the authorizer (Lambda or Cognito authorizer on the
REST API) if only the identity source changes but usage plans and gateway responses are still
wanted; that path keeps the Terraform module and the error contract intact.
