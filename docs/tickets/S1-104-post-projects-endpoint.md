---
title: "S1-104 POST /v1/projects returning 201, 400 and 409 problem+json"
labels: type:feature, pillar:security
milestone: S1 Create project
status: done
---
## Description
Route in `api/routes/projects.py`. 201 with the project body (camelCase) and a `Location` header; 400 problem+json with per-field `errors` on validation failure (replacing FastAPI's 422); 409 problem+json when the name is taken; 401 when no identity is present.

## Acceptance criteria
- Given a valid body and identity, then 201, `status` is `CREATED`, `ownerId` equals the caller's key id.
- Given the same name with different case, then 409 with `title: "Project name already exists"`.
- Given malformed JSON or an unknown field, then 400.

## Definition of Done
Integration tests in `tests/integration/test_projects_api.py` green for both TestClient and the Lambda handler path.
