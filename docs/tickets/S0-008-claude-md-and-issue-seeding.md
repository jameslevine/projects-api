---
title: "S0-008 CLAUDE.md conventions, ticket seed files and gh issue seeding script"
labels: type:chore, pillar:operations
milestone: S0 Foundation
status: done
---
## Description
`CLAUDE.md` with stack, commands, layout, rules and the branch/PR workflow. `docs/tickets/*.md` as the seed for GitHub Issues (front matter: title, labels, milestone, status). `scripts/seed_issues.py` creates labels, milestones and issues idempotently and closes tickets marked `done` with a reference to the implementing commit. `docs/tickets/README.md` explains the board.

## Acceptance criteria
- Given the script runs twice, then the second run creates nothing new.
- Given a ticket marked `done`, then its issue is closed with a comment naming the commit.

## Definition of Done
Issues visible in the repo, milestones populated.
