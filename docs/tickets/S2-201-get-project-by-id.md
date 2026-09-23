---
title: "S2-201 GET /v1/projects/{projectId}"
labels: type:feature, pillar:security
milestone: S2 Read projects
status: open
---
## Description
Add `GET /v1/projects/{projectId}` to `api/routes/projects.py`. Return 200 with the project body when the caller owns it. Return 404 problem+json when the project does not exist **or** belongs to another owner (no enumeration). Reuse `ProjectRepository.get` and `ProjectNotFoundError`. Validate the path parameter shape (`prj_` + 32 hex) and return 404 for malformed ids rather than 400.

## Acceptance criteria
- Given a project created by key A, when key A GETs it, then 200 and the body equals the create response.
- Given the same project, when key B GETs it, then 404 problem+json with `title: "Project not found"`.
- Given `prj_doesnotexist`, then 404.
- Given the Lambda handler path with a synthetic event, then 200 for the owner.

## Dependencies
None. Touches `api/routes/projects.py`, `repositories/projects.py` (if needed), `tests/integration/test_projects_api.py`.

## Definition of Done
Tests added; `make lint test` green; README API table updated if README exists.
