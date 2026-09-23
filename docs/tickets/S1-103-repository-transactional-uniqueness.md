---
title: "S1-103 ProjectRepository.create with transactional name reservation"
labels: type:feature, pillar:reliability
milestone: S1 Create project
status: done
---
## Description
`repositories/projects.py` writes the `PROJECT#<id>/META` item and the `NAME#<nameKey>/RESERVATION` item in one `TransactWriteItems` with `attribute_not_exists(PK)` conditions. A cancellation caused by the reservation condition raises `ProjectNameTakenError`. `get()` reads by id.

## Acceptance criteria
- Given a name already reserved (any case/whitespace variant), when creating, then `ProjectNameTakenError` and no partial project item is written.
- Given a create, then `GSI1PK=OWNER#<ownerId>` and `GSI1SK=PROJECT#<createdAt>#<projectId>` are set.

## Definition of Done
moto tests in `tests/unit/test_repository.py` green.
