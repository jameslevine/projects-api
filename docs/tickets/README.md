# Tickets and board

Tickets are **GitHub Issues** in this repository. The files in this directory are the seed
from which they were created (`scripts/seed_issues.py`) and are kept for history; once an
issue exists, edit the issue rather than the file.

## Board

- Milestones are feature slices, each shipping something usable on its own:
  - **S0 Foundation**: a deployed, monitored `GET /health` behind API Gateway.
  - **S1 Create project**: an API-key holder can create a project (201) or learn the name is taken (409).
  - **S2 Read projects**: owners can fetch and list their projects.
  - **S3 Operate**: on-call can see health, correlate requests, get paged and roll back.
  - **S4 Lifecycle**: delete, an async provisioning pipeline skeleton, a prod environment.
- Labels: `type:*` (feature, infra, docs, test, chore), `pillar:*` (security, reliability,
  performance, cost, operations), `slice:S0..S4`, `status:blocked`.
- Columns are issue states: open with no `Started` comment = Backlog, `Started` = In progress,
  PR open = In review, closed = Done.

## Flow

1. An agent (or human) takes an open issue in the current milestone and comments `Started`.
2. Work happens on `ticket/<ID>-<slug>`, following `CLAUDE.md`.
3. A PR titled `<ID>: <title>` with `Closes #<n>` is opened; CI must pass.
4. The orchestrator reviews, runs `make lint test` on the branch, and squash-merges.
5. When all issues in a milestone are closed, the milestone is closed and the next slice starts.

```bash
gh issue list --milestone "S2 Read projects" --state open
gh pr list --state open
gh issue view <n> --comments
```
