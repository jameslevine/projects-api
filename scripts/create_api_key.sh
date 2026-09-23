#!/usr/bin/env bash
# Onboard a user: create an API Gateway API key and attach it to the usage plan.
#
# Usage: scripts/create_api_key.sh <user-label> [env]
# Prints the key id (the ownerId the API will see) and the secret key value once.
set -euo pipefail

LABEL="${1:?usage: $0 <user-label> [env]}"
ENV="${2:-dev}"
TF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../infra/terraform/envs/${ENV}" && pwd)"

USAGE_PLAN_ID="$(terraform -chdir="${TF_DIR}" output -raw usage_plan_id)"
KEY_NAME="projects-api-${ENV}-${LABEL}"

KEY_JSON="$(aws apigateway create-api-key --name "${KEY_NAME}" --enabled \
  --tags Project=projects-api,Environment="${ENV}",User="${LABEL}" --output json)"
KEY_ID="$(echo "${KEY_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
KEY_VALUE="$(echo "${KEY_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["value"])')"

aws apigateway create-usage-plan-key --usage-plan-id "${USAGE_PLAN_ID}" \
  --key-id "${KEY_ID}" --key-type API_KEY >/dev/null

cat <<MSG
Created API key for '${LABEL}'
  ownerId (key id): ${KEY_ID}
  x-api-key value : ${KEY_VALUE}
Store the value securely. It cannot be retrieved again without 'aws apigateway get-api-key --include-value'.
MSG
