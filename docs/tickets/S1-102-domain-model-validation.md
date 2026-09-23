---
title: "S1-102 Domain model and server-side validation rules for project creation"
labels: type:feature, pillar:security
milestone: S1 Create project
status: done
---
## Description
`domain/validation.py` holds the name rules: trim, collapse whitespace, 3 to 63 characters, letters/digits/space/hyphen/underscore, alphanumeric first and last character; `name_key()` lower-cases for uniqueness. `domain/models.py` has `ProjectType` (`agent|mcp|web`), `ProjectStatus`, `CreateProjectRequest` (`extra="forbid"`) and `Project` with camelCase aliases.

## Acceptance criteria
- Given `"  My   App "`, when validated, then the stored name is `"My App"` and the key `"my app"`.
- Given `"ab"`, `"a"*64`, `"-x"`, `"a/b"`, `"<script>"`, then validation fails with a user-facing message.
- Given `type: "database"`, then validation fails.

## Definition of Done
Unit tests in `tests/unit/test_validation.py` and `test_models.py` green.
