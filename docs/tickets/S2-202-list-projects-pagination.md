---
title: "S2-202 GET /v1/projects: list the caller's projects with cursor pagination"
labels: type:feature, pillar:performance, pillar:cost
milestone: S2 Read projects
status: open
---
## Description
Add `GET /v1/projects?limit=&nextToken=` listing the caller's projects newest first via a `Query` on GSI1 (`GSI1PK = OWNER#<ownerId>`, `ScanIndexForward=False`). `limit` defaults to 20, range 1 to 100 (400 otherwise). `nextToken` is an opaque, URL-safe base64 encoding of `LastEvaluatedKey`; an invalid token returns 400 problem+json. Response: `{"items":[...], "nextToken": "..."|null}`. Add `ProjectRepository.list_by_owner(owner_id, limit, cursor)` returning items and the raw cursor.

## Acceptance criteria
- Given 3 projects for key A and 1 for key B, when key A lists with `limit=2`, then 2 newest items and a `nextToken`; following it returns the remaining 1 and `nextToken: null`; key B's project never appears.
- Given `limit=0` or `limit=101`, then 400.
- Given a tampered `nextToken`, then 400 with `title: "Invalid request"`.

## Dependencies
Same files as S2-201: implement on the same branch after S2-201, or after it is merged.

## Definition of Done
Unit tests for the cursor codec and repository; integration tests for the route; README API table updated if README exists.
