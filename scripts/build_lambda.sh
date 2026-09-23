#!/usr/bin/env bash
# Build the Lambda deployment package for python3.12 on arm64.
#
# Uses uv to resolve the locked runtime dependencies and install manylinux aarch64
# wheels regardless of the host platform, then zips them with the application code.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT}/build"
STAGE_DIR="${BUILD_DIR}/stage"
ZIP_PATH="${BUILD_DIR}/lambda.zip"
PY_VERSION="3.12"
PLATFORM="aarch64-manylinux2014"

rm -rf "${STAGE_DIR}" "${ZIP_PATH}"
mkdir -p "${STAGE_DIR}"

echo "==> Exporting locked runtime dependencies"
uv export --frozen --no-dev --no-hashes --no-emit-project --format requirements-txt \
  --output-file "${BUILD_DIR}/requirements.txt" >/dev/null

echo "==> Installing wheels for ${PLATFORM} / python${PY_VERSION}"
uv pip install \
  --python-platform "${PLATFORM}" \
  --python-version "${PY_VERSION}" \
  --only-binary :all: \
  --target "${STAGE_DIR}" \
  --no-compile \
  -r "${BUILD_DIR}/requirements.txt" >/dev/null

echo "==> Copying application code"
cp -R "${ROOT}/src/projects_api" "${STAGE_DIR}/projects_api"

echo "==> Pruning caches, tests and type stubs"
find "${STAGE_DIR}" -type d \( -name "__pycache__" -o -name "tests" -o -name "*.dist-info" \) -prune -exec rm -rf {} + 2>/dev/null || true
find "${STAGE_DIR}" -type f -name "*.pyc" -delete
# boto3/botocore ship in the Lambda runtime, but the pinned versions in the lockfile
# are kept so behaviour matches tests exactly. Remove the next two lines to shrink the zip.
# rm -rf "${STAGE_DIR}"/boto3 "${STAGE_DIR}"/botocore "${STAGE_DIR}"/s3transfer

echo "==> Zipping"
(cd "${STAGE_DIR}" && zip -qr -X "${ZIP_PATH}" . -x '*.DS_Store')

if unzip -l "${ZIP_PATH}" | grep "pydantic_core.*aarch64.*\.so" >/dev/null; then
  echo "==> OK: arm64 native wheels present"
else
  echo "!! pydantic_core arm64 wheel not found in package" >&2
  exit 1
fi

du -h "${ZIP_PATH}" | awk '{print "==> Built " $2 " (" $1 ")"}'
