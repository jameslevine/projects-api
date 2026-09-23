---
title: "S1-106 Local development loop with DynamoDB Local"
labels: type:chore, pillar:operations
milestone: S1 Create project
status: done
---
## Description
`docker-compose.yml` runs DynamoDB Local; `scripts/create_local_table.py` creates the table; `make run-local` starts uvicorn with `ENV=local` so the `X-Api-Key-Id` header acts as identity.

## Acceptance criteria
- Given `make local-db && make run-local`, when I POST to `localhost:8080/v1/projects` with `X-Api-Key-Id: demo`, then 201, and a second identical POST returns 409.

## Definition of Done
Documented in README.
