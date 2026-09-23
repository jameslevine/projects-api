#!/usr/bin/env bash
# Roll the `live` alias of the projects-api Lambda back to an earlier published version.
#
#   make rollback                              # dev: previous version, asks for confirmation
#   make rollback ENV=prod ARGS="--yes"        # prod: previous version, no prompt
#   scripts/rollback.sh --env dev --version 12 --dry-run
#
# Options:
#   --env dev|prod    environment (default: $ENV, else dev); the function is projects-api-<env>
#   --function NAME   override the function name
#   --version N       target published version (default: the highest version below the current one)
#   --yes, -y         do not ask for confirmation
#   --dry-run         print the update-alias command and exit without changing anything
#   -h, --help        show this help
#
# Exit codes: 0 success or dry run, 1 usage error or aborted, 2 nothing to roll back to,
# 3 AWS CLI error. AWS_CLI overrides the aws binary (the tests point it at a fake).
#
# Note: the alias is managed by Terraform. The next `terraform apply` publishes a new version
# and moves `live` forward again, so a rollback is a stop-gap while the fix is prepared.
#
# Bash 3.2 compatible (macOS /bin/bash): no mapfile, associative arrays or ${var^^}.
set -euo pipefail

AWS_CLI="${AWS_CLI:-aws}"
ALIAS_NAME="live"

usage() {
  sed -n '2,/^set -euo pipefail/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

die() { # exit-code message...
  local code="$1"
  shift
  echo "error: $*" >&2
  exit "$code"
}

aws_call() { # run the AWS CLI; on failure print its output and exit 3
  local out
  if ! out="$("$AWS_CLI" "$@" 2>&1)"; then
    echo "error: '${AWS_CLI} $*' failed:" >&2
    echo "$out" >&2
    exit 3
  fi
  printf '%s\n' "$out"
}

# ---- arguments ---------------------------------------------------------------------------

ENV_NAME="${ENV:-dev}"
FUNCTION=""
TARGET=""
ASSUME_YES=0
DRY_RUN=0

need_value() { # option
  [ $# -ge 2 ] || { usage >&2; die 1 "$1 requires a value"; }
}

while [ $# -gt 0 ]; do
  case "$1" in
    --env)      need_value "$@"; ENV_NAME="$2"; shift 2 ;;
    --env=*)    ENV_NAME="${1#--env=}"; shift ;;
    --function) need_value "$@"; FUNCTION="$2"; shift 2 ;;
    --function=*) FUNCTION="${1#--function=}"; shift ;;
    --version)  need_value "$@"; TARGET="$2"; shift 2 ;;
    --version=*) TARGET="${1#--version=}"; shift ;;
    --yes|-y)   ASSUME_YES=1; shift ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)  usage; exit 0 ;;
    *)          usage >&2; die 1 "unknown argument: $1" ;;
  esac
done

case "$ENV_NAME" in
  dev|prod) ;;
  *) die 1 "unknown environment '${ENV_NAME}' (expected dev or prod)" ;;
esac
FUNCTION="${FUNCTION:-projects-api-${ENV_NAME}}"
if [ -n "$TARGET" ] && ! [[ "$TARGET" =~ ^[0-9]+$ ]]; then
  die 1 "--version must be a published version number, got '${TARGET}'"
fi

# ---- current state -----------------------------------------------------------------------

CURRENT="$(aws_call lambda get-alias --function-name "$FUNCTION" --name "$ALIAS_NAME" \
  --query FunctionVersion --output text)"

# One line per published version: "<version>\t<last modified>\t<description>", numerically sorted.
# The CLI paginates list-versions-by-function on its own.
VERSIONS="$(aws_call lambda list-versions-by-function --function-name "$FUNCTION" \
  --query "Versions[?Version!='\$LATEST'].[Version,LastModified,Description]" --output text \
  | awk -F'\t' '$1 ~ /^[0-9]+$/' | sort -t "$(printf '\t')" -k1,1n)"

[ -n "$VERSIONS" ] || die 2 "${FUNCTION} has no published versions; nothing to roll back to"

# ---- pick the target -----------------------------------------------------------------------

version_exists() { # version
  printf '%s\n' "$VERSIONS" | awk -F'\t' -v v="$1" '$1 == v { found = 1 } END { exit !found }'
}

if [ -z "$TARGET" ]; then
  if ! [[ "$CURRENT" =~ ^[0-9]+$ ]]; then
    die 2 "${FUNCTION}:${ALIAS_NAME} points at '${CURRENT}', not a published version; pass --version N"
  fi
  # Highest published version strictly below the current one.
  TARGET="$(printf '%s\n' "$VERSIONS" | awk -F'\t' -v cur="$CURRENT" '$1 + 0 < cur + 0 { t = $1 } END { print t }')"
  [ -n "$TARGET" ] || die 2 "${FUNCTION}:${ALIAS_NAME} is at version ${CURRENT}; no earlier published version exists"
else
  version_exists "$TARGET" || die 2 "version ${TARGET} is not a published version of ${FUNCTION}"
  [ "$TARGET" != "$CURRENT" ] || die 2 "${FUNCTION}:${ALIAS_NAME} already points at version ${TARGET}"
fi

# ---- before / after --------------------------------------------------------------------------

row_for() { # version -> "version\tlast modified\tdescription"
  printf '%s\n' "$VERSIONS" | awk -F'\t' -v v="$1" '$1 == v { print; exit }'
}

print_row() { # marker version modified description
  printf '  %-8s %-8s %-30s %s\n' "$1" "$2" "$3" "$4"
}

echo "Function : ${FUNCTION}"
echo "Alias    : ${ALIAS_NAME}"
echo
echo "Published versions (* = current, > = target):"
print_row "" "version" "last modified" "description"
while IFS="$(printf '\t')" read -r ver modified desc; do
  marker=""
  [ "$ver" = "$CURRENT" ] && marker="*"
  [ "$ver" = "$TARGET" ] && marker=">"
  print_row "$marker" "$ver" "$modified" "$desc"
done <<EOF
$VERSIONS
EOF
echo
echo "Before: ${ALIAS_NAME} -> ${CURRENT}"
echo "After : ${ALIAS_NAME} -> ${TARGET}"
if [ "$TARGET" -gt "${CURRENT:-0}" ] 2>/dev/null; then
  echo "warning: version ${TARGET} is newer than the current ${CURRENT}; this rolls forward, not back."
fi
echo

UPDATE_CMD="${AWS_CLI} lambda update-alias --function-name ${FUNCTION} --name ${ALIAS_NAME} --function-version ${TARGET}"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry run: nothing changed. Would run:"
  echo "  ${UPDATE_CMD}"
  exit 0
fi

if [ "$ASSUME_YES" -ne 1 ]; then
  printf 'Repoint %s:%s from version %s to %s? [y/N] ' "$FUNCTION" "$ALIAS_NAME" "$CURRENT" "$TARGET"
  answer=""
  read -r answer || true
  case "$answer" in
    y|Y|yes|YES) ;;
    *) echo "aborted; nothing changed."; exit 1 ;;
  esac
fi

# ---- apply and confirm -------------------------------------------------------------------------

aws_call lambda update-alias --function-name "$FUNCTION" --name "$ALIAS_NAME" \
  --function-version "$TARGET" >/dev/null
AFTER="$(aws_call lambda get-alias --function-name "$FUNCTION" --name "$ALIAS_NAME" \
  --query FunctionVersion --output text)"
if [ "$AFTER" != "$TARGET" ]; then
  die 3 "${FUNCTION}:${ALIAS_NAME} now points at '${AFTER}', expected ${TARGET}"
fi

echo "done: ${FUNCTION}:${ALIAS_NAME} now points at version ${TARGET} (was ${CURRENT})."
echo "note: the next 'terraform apply' publishes a new version and moves '${ALIAS_NAME}' forward again."
echo "next: run 'make smoke ENV=${ENV_NAME}' to verify the rolled-back stage."
