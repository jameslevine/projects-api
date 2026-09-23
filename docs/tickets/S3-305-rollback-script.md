---
title: "S3-305 Rollback script for the live Lambda alias"
labels: type:chore, pillar:reliability, pillar:operations
milestone: S3 Operate
status: open
---
## Description
`scripts/rollback.sh [env] [version]`: lists published versions of the function (`aws lambda list-versions-by-function`), shows which one `live` points to, and repoints the alias to the given version (default: the previous one). Print before/after. Add `make rollback` and document in the runbook. Note in the script that a later `terraform apply` will move the alias forward again.

## Acceptance criteria
- Given no version argument, then the script picks the version immediately before the current one and asks for confirmation unless `--yes`.
- Given `--dry-run`, then nothing is changed.

## Dependencies
After S3-302 (keep PRs sequential to avoid Makefile conflicts).

## Definition of Done
Script is executable, shellcheck-clean, documented.
