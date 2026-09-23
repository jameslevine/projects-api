---
title: "S4-403 ADR 0005: per-type provisioning design (agent, mcp, web)"
labels: type:docs, pillar:security, pillar:cost
milestone: S4 Lifecycle
status: open
---
## Description
Write `docs/adr/0005-per-type-provisioning.md`. For each `ProjectType` propose the AWS resources a READY project gets (for example web: S3 + CloudFront with a per-project path or subdomain; mcp: Lambda function URL or API Gateway route with per-project key; agent: Lambda or ECS task with a queue), how naming maps from the project name (`nameKey` to DNS label), tenant isolation and IAM boundaries, quotas per owner, cost per idle project and per active project, teardown on delete, and what remains out of scope. Include a Mermaid sequence diagram of create, stream, provisioner, READY. State explicitly what S4-402 already implements and what is future work.

## Acceptance criteria
- Given the ADR, then it has Status (Proposed), Context, Options considered, Decision, Consequences, and a per-type table of resources, isolation and estimated monthly cost.

## Definition of Done
Merged, linked from `docs/architecture.md`.
