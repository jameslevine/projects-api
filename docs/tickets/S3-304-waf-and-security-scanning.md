---
title: "S3-304 Optional WAF WebACL and Terraform security scanning in CI"
labels: type:infra, pillar:security, pillar:cost
milestone: S3 Operate
status: open
---
## Description
Add `enable_waf` (default `false`, for cost) to `envs/dev` and `modules/api_gateway_rest`: when true, create a REGIONAL `aws_wafv2_web_acl` with `AWSManagedRulesCommonRuleSet`, `AWSManagedRulesKnownBadInputsRuleSet` and a rate-based rule (2000 requests per 5 minutes per IP), and associate it with the stage. Add `tflint` and `checkov` (or `trivy config`) jobs to `.github/workflows/ci.yml` with a baseline/skip file for accepted findings, each documented.

## Acceptance criteria
- Given `enable_waf=false`, then no WAF resources are planned; given `true`, then `terraform validate` passes and the association targets the stage ARN.
- Given CI, then tflint and the security scanner run on `infra/terraform` and pass.

## Dependencies
After S3-301 (same module directory).

## Definition of Done
`make tf-fmt tf-validate` green; CI green.
