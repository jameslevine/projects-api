---
title: "S0-004 Terraform modules lambda_api and api_gateway_rest, dev environment wiring"
labels: type:infra, pillar:security, pillar:performance, pillar:cost
milestone: S0 Foundation
status: done
---
## Description
`modules/lambda_api`: python3.12 arm64 function, role with basic execution + X-Ray, 14-day log group, `live` alias, tracing on. `modules/api_gateway_rest`: REGIONAL REST API, `GET /health` public, `ANY /{proxy+}` with `api_key_required`, Lambda proxy integrations, stage `live` with structured access logs (no bodies), method settings (metrics, throttling), problem+json gateway responses for 401/403/429, usage plan + demo key, Lambda permission scoped to the API. `envs/dev` wires table, lambda, api and observability modules with an S3 partial backend.

## Acceptance criteria
- Given `envs/dev`, when I run `terraform init -backend=false && terraform validate`, then it succeeds.
- Given an apply, when I `GET <invoke_url>/health` without a key, then 200; when I `POST /v1/projects` without a key, then 403 problem+json.

## Definition of Done
`make tf-fmt tf-validate` green locally and in CI.
