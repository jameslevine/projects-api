#!/usr/bin/env bash
# Smoke test against a deployed stage. Requires terraform outputs (or API_URL / API_KEY env vars).
#
#   make smoke                    # reads outputs from infra/terraform/envs/dev
#   API_URL=... API_KEY=... tests/smoke/smoke.sh
set -euo pipefail

ENV="${ENV:-dev}"
TF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../infra/terraform/envs/${ENV}" && pwd)"
API_URL="${API_URL:-$(terraform -chdir="${TF_DIR}" output -raw api_url)}"
API_KEY="${API_KEY:-$(terraform -chdir="${TF_DIR}" output -raw demo_api_key_value)}"
NAME="smoke $(date +%s)"

pass=0; fail=0
check() { # label expected actual
  if [[ "$2" == "$3" ]]; then echo "PASS $1 ($3)"; pass=$((pass+1)); else echo "FAIL $1 expected $2 got $3"; fail=$((fail+1)); fi
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

check "GET /health without key"          200 "$(code "${API_URL}/health")"
check "POST /v1/projects without key"    403 "$(code -X POST "${API_URL}/v1/projects" -H 'content-type: application/json' -d '{"name":"x","type":"web"}')"
check "POST /v1/projects create"         201 "$(code -X POST "${API_URL}/v1/projects" -H "x-api-key: ${API_KEY}" -H 'content-type: application/json' -d "{\"name\":\"${NAME}\",\"type\":\"web\"}")"
check "POST /v1/projects duplicate"      409 "$(code -X POST "${API_URL}/v1/projects" -H "x-api-key: ${API_KEY}" -H 'content-type: application/json' -d "{\"name\":\"$(printf "%s" "${NAME}" | tr "[:lower:]" "[:upper:]")\",\"type\":\"agent\"}")"
check "POST /v1/projects invalid name"   400 "$(code -X POST "${API_URL}/v1/projects" -H "x-api-key: ${API_KEY}" -H 'content-type: application/json' -d '{"name":"a/b","type":"web"}')"

echo "${pass} passed, ${fail} failed"
[[ ${fail} -eq 0 ]]
