---
title: "S3-302 Request correlation: gateway request id in logs and responses"
labels: type:feature, pillar:operations
milestone: S3 Operate
status: open
---
## Description
Set Powertools `correlation_id_path=correlation_paths.API_GATEWAY_REST` on the logger decorator so every log line carries the API Gateway `requestId`. Add a middleware that logs one structured line per request with `route`, `method`, `status`, `ownerId` (key id, never the key value) and `durationMs`. `X-Request-Id` on every response (success and problem) should be the API Gateway request id when present, else the Lambda request id, else a generated UUID.

## Acceptance criteria
- Given the Lambda handler path with a synthetic event, then the 201 response has `x-request-id` equal to `requestContext.requestId` and the problem body `requestId` matches on errors.
- Given local TestClient, then `X-Request-Id` is a UUID.
- Given the per-request log line, then it never contains the request body or `x-api-key`.

## Dependencies
Touches `main.py` and the `request_id` helper in `api/errors.py`. S3-301 also edits `api/errors.py`: keep changes minimal and localised.

## Definition of Done
Tests + `make lint test` green.
