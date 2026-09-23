---
title: "S0-005 Lambda build script producing an arm64 zip"
labels: type:chore, pillar:performance, pillar:cost
milestone: S0 Foundation
status: done
---
## Description
`scripts/build_lambda.sh` exports locked runtime dependencies with `uv export`, installs `aarch64-manylinux2014` wheels for Python 3.12 into a staging directory, copies `src/projects_api`, prunes caches and zips to `build/lambda.zip`.

## Acceptance criteria
- Given the script, when it runs on macOS or Linux CI, then `build/lambda.zip` exists and contains a `pydantic_core*aarch64*.so`.
- Given a change to `uv.lock`, then the next build picks it up (no manual requirements file).

## Definition of Done
`make build` works locally and the CI job uploads the zip artefact.
