---
title: "S4-401 DELETE /v1/projects/{projectId} releasing the name reservation"
labels: type:feature, pillar:reliability, pillar:security
milestone: S4 Lifecycle
status: open
---
## Description
Add `ProjectRepository.delete(project_id, owner_id)` that, in one `TransactWriteItems`, deletes the `PROJECT#<id>/META` item with condition `attribute_exists(PK) AND ownerId = :owner` and deletes `NAME#<nameKey>/RESERVATION` with condition `projectId = :id`. Route returns 204 on success, 404 for missing or another owner's project. Emit a `ProjectsDeleted` metric.

## Acceptance criteria
- Given owner A deletes their project, then 204 and a subsequent create with the same name succeeds (201).
- Given owner B deletes A's project, then 404 and nothing is removed.
- Given a second delete of the same id, then 404.

## Dependencies
S2-201 merged (shared route file and get semantics).

## Definition of Done
Tests, README API table, ADR 0003 updated with the release path.
