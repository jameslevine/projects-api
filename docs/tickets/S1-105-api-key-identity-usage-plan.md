---
title: "S1-105 API key identity: usage plan, demo key, gateway responses, key onboarding script"
labels: type:feature, type:infra, pillar:security, pillar:cost
milestone: S1 Create project
status: done
---
## Description
`api_key_required=true` on `/{proxy+}`; usage plan with per-key throttle and monthly quota; a demo key attached at apply time; problem+json gateway responses for UNAUTHORIZED, INVALID_API_KEY and THROTTLED; `api/deps.py::current_user` reads `requestContext.identity.apiKeyId` with a local-only header fallback; `scripts/create_api_key.sh <label>` creates and attaches new keys.

## Acceptance criteria
- Given a request without `x-api-key`, then API Gateway returns 403 problem+json without invoking Lambda.
- Given `ENV=dev`, when the `X-Api-Key-Id` header is sent without a gateway, then it is ignored (401).

## Definition of Done
Terraform validated; dependency covered by integration tests.
