---
title: "S0-001 Repo scaffold: uv, ruff, mypy, pytest, Makefile"
labels: type:chore, pillar:operations
milestone: S0 Foundation
status: done
---
## Description
Create the Python project with `uv`, pinned to Python 3.12, with ruff (lint + format), mypy strict, pytest, a Makefile with the standard targets and a `.gitignore` covering Python, Terraform and local files.

## Acceptance criteria
- Given a fresh clone, when I run `uv sync && make lint test`, then both pass.
- Given `pyproject.toml`, then runtime and dev dependencies are separated and locked in `uv.lock`.

## Definition of Done
Code merged, `make lint test` green, CLAUDE.md describes the commands.
