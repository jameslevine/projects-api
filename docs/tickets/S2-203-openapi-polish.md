---
title: "S2-203 OpenAPI polish: problem schema, examples, schema contract test"
labels: type:docs, type:test, pillar:operations
milestone: S2 Read projects
status: open
---
## Description
Make `/v1/openapi.json` accurate and useful: define a reusable `Problem` schema component and reference it from every 4xx/5xx response of every route; add request/response examples; set tags, summaries and `operationId`s; include the `x-api-key` API key security scheme so generated clients send it. Add a contract test that loads the schema via TestClient, validates it with `openapi-spec-validator` (add as dev dependency) and asserts each route's error responses reference `Problem`.

## Acceptance criteria
- Given `/v1/openapi.json`, then it validates as OpenAPI 3.1 and every non-2xx response has `content: application/problem+json` referencing `#/components/schemas/Problem`.
- Given the schema, then `securitySchemes.ApiKeyAuth` is `type: apiKey, in: header, name: x-api-key` and applied globally except `/health`.

## Dependencies
Do not edit route logic in `api/routes/projects.py` (S2-201/202 own it); use FastAPI `responses=` metadata on routers and a post-processing `custom_openapi` in `main.py` instead.

## Definition of Done
Contract test green; `make lint test` green.
