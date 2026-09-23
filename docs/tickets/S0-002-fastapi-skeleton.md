---
title: "S0-002 FastAPI skeleton with /health, Mangum handler and problem+json errors"
labels: type:feature, pillar:operations
milestone: S0 Foundation
status: done
---
## Description
FastAPI application factory, `GET /health`, Mangum Lambda `handler` wrapped with Powertools logger/tracer/metrics, and RFC 7807 `application/problem+json` handlers for validation errors, HTTP errors and unhandled exceptions.

## Acceptance criteria
- Given the app, when I `GET /health`, then I get 200 `{"status":"ok","version":...}`.
- Given any error, then the response is `application/problem+json` with `type`, `title`, `status`, `detail`, `instance` and, when available, `requestId`.
- Given a Lambda invocation with a synthetic API Gateway REST event, when the handler runs, then the response body is plain JSON (not base64) for both success and problem responses.

## Definition of Done
Integration tests cover the above; `make lint test` green.
