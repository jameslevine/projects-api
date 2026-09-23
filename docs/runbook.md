# Projects API: operations runbook

For the on-call engineer. Everything here describes what the repository deploys today; work
that is still open is linked by issue number in section 9. Names use `<env>`; the only environment that exists is `dev`
(`projects-api-dev`). Production is [#28](https://github.com/jameslevine/projects-api/issues/28).

Companion documents: [architecture.md](architecture.md) (components, data model, request flow),
[adr/](adr/) (decisions), the [README](../README.md) (commands and API reference).

Standing rule from [CLAUDE.md](../CLAUDE.md): do not run `terraform apply` or mutating `aws`
commands unless you mean to. Every command below that changes something says so.

## 1. Service overview

The Projects API is a FastAPI application running on one AWS Lambda function (Python 3.12,
arm64) behind an API Gateway REST API, storing everything in one DynamoDB table. A caller sends
`x-api-key`; API Gateway validates the key against a usage plan and the key's **id** becomes the
`ownerId` of everything that caller creates. Endpoints: `GET /health` (public),
`POST /v1/projects`, `GET /v1/projects`, `GET /v1/projects/{projectId}` (key required).

Region: **eu-west-2** (London). Everything is tagged `Project=projects-api`,
`Environment=<env>`, `ManagedBy=terraform`.

| Component | Name / location | Defined in |
|---|---|---|
| REST API | `projects-api-<env>`, regional, stage `live` | `infra/terraform/modules/api_gateway_rest` |
| Usage plan | `projects-api-<env>-default` (10 req/s, burst 20, 10,000 req/month per key) | same |
| Demo API key | `projects-api-<env>-demo` (created by Terraform) | same |
| Stage throttle | 50 req/s, burst 100 | same |
| Access log group | `/aws/apigateway/projects-api-<env>/access` (JSON, 14-day retention) | same |
| Lambda function | `projects-api-<env>`, alias `live`, 512 MB, 10 s timeout, unreserved concurrency | `infra/terraform/modules/lambda_api` |
| Lambda log group | `/aws/lambda/projects-api-<env>` (14-day retention) | same |
| Lambda IAM role | `projects-api-<env>-role` (DynamoDB actions on the table ARN and its indexes only) | same |
| DynamoDB table | `projects-api-<env>`, on-demand, PITR on, GSI `GSI1`, deletion protection only when `<env>` is `prod` | `infra/terraform/modules/dynamodb_table` |
| Dashboard | `projects-api-<env>` | `infra/terraform/modules/observability` |
| Alarm topic | SNS `projects-api-<env>-alarms` | same |
| Budget | `projects-api-<env>-monthly` (default USD 20) | same |
| Custom metrics | CloudWatch namespace `ProjectsApi`: `ProjectsCreated` and `ProjectNameConflicts` (dimension `service=projects-api`), `ColdStart` (dimensions `function_name=projects-api-<env>` and `service=projects-api`) | `src/projects_api/observability.py`, `api/routes/projects.py`, `api/errors.py` |
| Terraform state | S3 bucket from `infra/terraform/bootstrap`, key `projects-api/<env>/terraform.tfstate`, lock table `projects-api-terraform-locks` | `infra/terraform/envs/<env>/backend.hcl` (not committed) |

Console shortcuts (dev):

- Dashboard: `https://eu-west-2.console.aws.amazon.com/cloudwatch/home?region=eu-west-2#dashboards:name=projects-api-dev`
- Alarms: `https://eu-west-2.console.aws.amazon.com/cloudwatch/home?region=eu-west-2#alarmsV2:?~(search~'projects-api-dev)`
- Logs Insights: `https://eu-west-2.console.aws.amazon.com/cloudwatch/home?region=eu-west-2#logsV2:logs-insights`
- X-Ray traces: `https://eu-west-2.console.aws.amazon.com/cloudwatch/home?region=eu-west-2#xray:traces`

Who gets paged: the SNS topic has an email subscription only if `alarm_email` is set in
`infra/terraform/envs/<env>/<env>.tfvars`. In the committed `dev.tfvars` it is commented out, so
by default **nobody is subscribed** and alarms only change state in the console. Set it before
relying on any alarm ([README, Deploy step 2](../README.md#deploy)) and confirm the subscription
email. Check `aws sns list-subscriptions-by-topic --topic-arn <alarm_topic_arn>` if you are unsure.
Every alarm sends both ALARM and OK transitions to the topic, so recovery is notified too.

Useful Terraform outputs (`terraform -chdir=infra/terraform/envs/<env> output`): `api_url`,
`demo_api_key_id`, `demo_api_key_value` (sensitive, use `-raw`), `usage_plan_id`, `table_name`,
`lambda_function_name`, `dashboard_name`, `waf_web_acl_arn` (null unless `enable_waf`).

## 2. Deploy

Prerequisites:

- AWS credentials for the target account in your shell (`aws sts get-caller-identity` works),
  region `eu-west-2`.
- Terraform >= 1.3, AWS CLI v2, `uv` (the zip build uses it).
- `infra/terraform/envs/<env>/backend.hcl`: copy `backend.example.hcl` (`cp -f`, this machine
  aliases `cp` to `cp -iv`) and set `bucket` to the state bucket created by
  `make tf-bootstrap STATE_BUCKET=<name>` (one-off per account). The file is git-ignored.
- `make tf-init` once per clone (`terraform init -backend-config=backend.hcl`).
- On a clean checkout, `make lint test` should be green.

Procedure (`ENV` defaults to `dev`; `make tf-plan` runs `make build` first, so step 1 is only
needed if you want to inspect the zip):

```bash
make build                 # scripts/build_lambda.sh -> build/lambda.zip (arm64 wheels, fails if pydantic_core arm64 .so is missing)
make tf-plan ENV=dev       # builds the zip, then terraform plan -var-file=dev.tfvars -out=tfplan
```

Review the plan. The saved plan file is `infra/terraform/envs/dev/tfplan`. Expect:

- A code change: `aws_lambda_function.this` updated in place (`source_code_hash`), a new
  published version, and `aws_lambda_alias.live` moved to it.
- An API definition change: `aws_api_gateway_deployment.this` replaced
  (`create_before_destroy`) and the stage repointed. The previous deployment is destroyed, see
  section 3.
- Anything that says `destroy` on the DynamoDB table, the log groups or the SNS topic is wrong;
  stop and ask.

```bash
make tf-apply ENV=dev      # terraform apply tfplan  (CHANGES AWS)
make smoke ENV=dev         # tests/smoke/smoke.sh against api_url with the demo key; expect "5 passed, 0 failed"
```

`make tf-apply` applies exactly the saved `tfplan`; if the plan is stale (someone else applied
in between) Terraform refuses and you re-run `make tf-plan`. Note that
[#16](https://github.com/jameslevine/projects-api/issues/16) tracks the fact that the smoke test
has not yet been run against a real stage.

After the apply, on dashboard `projects-api-<env>` for the next 10 to 15 minutes:

- "API requests and errors": `Count` non-zero from the smoke test, `5XXError` flat at zero.
- "API latency (ms)": p99 back below `lambda_p99_ms_threshold` (2000 ms) after the first
  cold starts.
- "Lambda invocations, errors, throttles": `Errors` and `Throttles` zero.
- "Business: projects created vs name conflicts": one `ProjectsCreated` and one
  `ProjectNameConflicts` from the smoke test, plus a `ColdStart` for each new execution
  environment.
- "DynamoDB consumed capacity and errors": some consumed read and write capacity, and
  `ReadThrottleEvents`, `WriteThrottleEvents` and "SystemErrors (all operations)" flat at zero.
- Alarm list filtered on `projects-api-<env>`: everything `OK` or `INSUFFICIENT_DATA`
  (the latter is normal on a quiet stage because `treat_missing_data = notBreaching`).

Also confirm the alias moved:

```bash
aws lambda get-alias --function-name projects-api-dev --name live --query FunctionVersion
```

## 3. Rollback

### Lambda: repoint the `live` alias

Every apply publishes a new immutable Lambda version (`publish = true`) and moves the alias
`live` to it. API Gateway invokes the alias, never `$LATEST`, so rollback is repointing the
alias and takes effect on the next invocation. Old versions are not deleted by Terraform.

```bash
# 1. What is live now, and what versions exist ($LATEST is not a candidate)
aws lambda get-alias --function-name projects-api-dev --name live \
  --query '{Version:FunctionVersion,Updated:RevisionId}'
aws lambda list-versions-by-function --function-name projects-api-dev \
  --query 'Versions[?Version!=`$LATEST`].{Version:Version,LastModified:LastModified,Sha:CodeSha256}' \
  --output table

# 2. Repoint (CHANGES AWS). <n> is the previous known-good version number.
aws lambda update-alias --function-name projects-api-dev --name live --function-version <n>

# 3. Verify
aws lambda get-alias --function-name projects-api-dev --name live --query FunctionVersion
curl -s "$(terraform -chdir=infra/terraform/envs/dev output -raw api_url)/health"
```

Then watch `projects-api-<env>-lambda-errors` and `projects-api-<env>-api-5xx` return to OK.

Caveats:

- The **next `terraform apply` moves the alias forward again**, because Terraform still holds
  the newest version in state. A rollback is a stop-gap; the real fix is a revert commit on
  `main` and a normal deploy (which publishes a new version containing the old code).
- Environment variables (`TABLE_NAME`, `LOG_LEVEL`, ...) are baked into each version. Rolling
  back also rolls back configuration.
- `make rollback` (`scripts/rollback.sh`, see `scripts/rollback.sh --help`) wraps steps 1 to 3
  with a confirmation prompt; `ENV=prod ARGS="--version N --yes"` selects the environment and
  version, and `--dry-run` only prints the commands. The manual steps above remain the reference
  for what it does.

### API Gateway: repoint the stage to an earlier deployment

Only relevant when the failure is in the API definition (routes, gateway responses, validator,
integration), not in code.

```bash
REST_API_ID="$(aws apigateway get-rest-apis --query "items[?name=='projects-api-dev'].id" --output text)"
aws apigateway get-stage --rest-api-id "${REST_API_ID}" --stage-name live --query deploymentId
aws apigateway get-deployments --rest-api-id "${REST_API_ID}" --query 'items[].{id:id,createdDate:createdDate,description:description}' --output table

# CHANGES AWS
aws apigateway update-stage --rest-api-id "${REST_API_ID}" --stage-name live \
  --patch-operations op=replace,path=/deploymentId,value=<previousDeploymentId>
```

Caveat: `aws_api_gateway_deployment.this` uses `create_before_destroy`, so Terraform **destroys
the previous deployment** once the stage points at the new one. `get-deployments` will usually
list only the current deployment, and this rollback is only possible if an older deployment
still exists. The dependable rollback path is the Lambda alias above, or a revert commit.

## 4. API key lifecycle

The key **id** is the identity (`requestContext.identity.apiKeyId` -> `ownerId` on every project
and `OWNER#<keyId>` in GSI1). The key **value** is the secret the user sends as `x-api-key`. Never
log or paste a key value; the code never sees it.

Create (CHANGES AWS; needs Terraform outputs, so run from a clone with `backend.hcl`):

```bash
scripts/create_api_key.sh <label> [env]      # env defaults to dev
scripts/create_api_key.sh alice dev
```

This creates key `projects-api-<env>-<label>` tagged `Project`, `Environment`, `User`, attaches
it to usage plan `usage_plan_id` and prints the id (the ownerId) and the value **once**. The value
can be recovered later only with `aws apigateway get-api-key --api-key <id> --include-value`.

Find a key id from its label (`--name-query` is a prefix match on the key name):

```bash
aws apigateway get-api-keys --name-query projects-api-dev-alice \
  --query 'items[].{id:id,name:name,enabled:enabled,created:createdDate}' --output table
aws apigateway get-api-keys --name-query projects-api-dev- --query 'items[].name'   # all keys for the env
```

Disable (CHANGES AWS). Requests with the key fail at the gateway with the `403` problem+json
within a minute or so; nothing reaches Lambda:

```bash
aws apigateway update-api-key --api-key <id> --patch-operations op=replace,path=/enabled,value=false
aws apigateway get-api-key --api-key <id> --query enabled                              # verify: false
```

Re-enable with `value=true`.

Rotate (CHANGES AWS): create the new key with a new label (for example `alice-2026-09`), hand the
value to the user, wait for their traffic to move (section 4, per-key usage), then disable the old
key. Do not delete it (below). Note that the new key is a **new identity**: projects created with
the old key stay owned by the old key id and will not be visible to the new key. If the user
needs to keep their existing projects, disabling and re-enabling the same key is the only option
today; ownership transfer is not implemented.

Per-key usage (also shows whether a key is still in use before you disable it):

```bash
USAGE_PLAN_ID="$(terraform -chdir=infra/terraform/envs/dev output -raw usage_plan_id)"
aws apigateway get-usage --usage-plan-id "${USAGE_PLAN_ID}" --key-id <id> \
  --start-date 2026-09-01 --end-date 2026-09-30
```

The result maps the key id to `[used, remaining]` per day against the 10,000/month quota. To see
who is calling right now, use the access log (`stats count(*) by apiKeyId`, section 6).

Delete (CHANGES AWS, avoid): `aws apigateway delete-api-key --api-key <id>`. The key id is the
`ownerId` stored on that user's project items and name reservations. Deleting the key does not
delete the data; it leaves **orphaned projects** that no key can ever read again and name
reservations that nobody can release (deletion is [#25](https://github.com/jameslevine/projects-api/issues/25)).
Disable instead, and only delete once the projects have been dealt with.

The demo key `projects-api-<env>-demo` is Terraform-managed: disable it with the same
`update-api-key` command if it leaks (Terraform will re-enable it on the next apply unless the
module is changed), or remove it from the module.

## 5. Tracing a request

### Which id is which

Two ids exist for one request, and they differ:

- **API Gateway `requestId`** (`$context.requestId`): minted by the gateway, written to the
  access log as `requestId`, returned to the client as `X-Request-Id` on every response (success
  and problem) and as `requestId` in every problem+json body, and stamped on every Lambda log
  line of that invocation as `correlation_id`. This is the id a user quotes and the one to
  search for.
- **Lambda `aws_request_id`**: minted by the Lambda service per invocation; Powertools writes it
  on every log line as `function_request_id`, and it is the `RequestId` in the runtime's
  `START`/`END`/`REPORT` lines. It never appears in the access log and the client never sees it.

How the id is chosen (`src/projects_api/api/context.py`, resolved once per request): the gateway
`requestContext.requestId` if present; otherwise the Lambda `aws_request_id` (a direct
invocation with no gateway); otherwise an incoming `X-Request-Id` header if it is 1 to 128
printable characters (local runs behind another proxy); otherwise a fresh UUID4. Behind the
gateway the first rule always applies, so header, problem body, access log and `correlation_id`
all carry the same value.

What the Lambda log group gets per request: `RequestContextMiddleware` writes one
`request completed` line with `route` (the route template, for example
`/v1/projects/{project_id}`), `method`, `status`, `owner_id` (the API key id, never the key
value), `duration_ms` and `request_id`; never bodies, query strings or headers. Powertools
(`correlation_id_path=API_GATEWAY_REST` on the handler in `main.py`, and
`logger.set_correlation_id` in the middleware) adds `correlation_id` to that line and to every
other line of the invocation, including `project created` and `Unhandled error`. Mangum logs a
second INFO line per request of the form `POST /v1/projects 201` (method, path and status only).
Requests rejected by the gateway (missing key -> 403, throttled -> 429) appear only in the access
log: there is no Lambda invocation to find.

### Access log (`/aws/apigateway/projects-api-<env>/access`)

```text
fields @timestamp, status, path, latencyMs, apiKeyId
| filter requestId = "<id>"
```

Add `httpMethod, integrationMs, errorMessage, ip, userAgent` for more detail. `errorMessage` is
set for gateway-generated errors (for example `Forbidden`, `Invalid API Key identifier
specified`). `integrationMs` is time spent in Lambda; `latencyMs - integrationMs` is gateway
overhead.

### Lambda log (`/aws/lambda/projects-api-<env>`)

With the gateway id (the normal case; it is the `X-Request-Id` the user quotes):

```text
fields @timestamp, level, message, route, method, status, duration_ms, cold_start, xray_trace_id
| filter correlation_id = "<id>"
| sort @timestamp asc
```

When you only have a Lambda id (from a `REPORT` line or an X-Ray segment):

```text
fields @timestamp, level, message, correlation_id, cold_start, xray_trace_id
| filter function_request_id = "<id>"
| sort @timestamp asc
```

The result includes the `request completed` line, so this also recovers the gateway id.

Logs written by versions deployed before request correlation existed carry no `correlation_id`
(and their `requestId`/`X-Request-Id` was the Lambda id). For those, join through the access log
timestamp: take `@timestamp` and `latencyMs` from the access log query, then in the Lambda group
narrow the time range to that second and look for the `REPORT` line and any `ERROR` line:

```text
fields @timestamp, @type, @requestId, @duration, @maxMemoryUsed, @message
| filter @type = "REPORT" or level = "ERROR"
| sort @timestamp asc
```

Running Logs Insights from the CLI:

```bash
QID="$(aws logs start-query --log-group-name /aws/apigateway/projects-api-dev/access \
  --start-time "$(date -v-1H +%s)" --end-time "$(date +%s)" \
  --query-string 'fields @timestamp, status, path, latencyMs, apiKeyId | filter requestId = "<id>"' \
  --query queryId --output text)"
aws logs get-query-results --query-id "${QID}"      # repeat until status is Complete
```

### X-Ray

Active tracing is on at both the stage and the function. Every Powertools log line carries
`xray_trace_id`; take it from either Lambda query above and fetch the trace:

```bash
aws xray batch-get-traces --trace-ids <xray_trace_id>
```

To find traces without a log line, filter by URL and status within a window:

```bash
aws xray get-trace-summaries --start-time "$(date -v-1H +%s)" --end-time "$(date +%s)" \
  --filter-expression 'http.url CONTAINS "/v1/projects" AND http.status = 500'
```

Segments: `projects-api-<env>/live` (gateway), `projects-api-<env>` (Lambda, with the
`## handler` subsegment from `capture_lambda_handler`) and `DynamoDB` calls made by boto3.
Response bodies are not captured (`POWERTOOLS_TRACER_CAPTURE_RESPONSE=false`); exceptions are.

### Reading a project the request touched

Take `project_id` from the `project created` log line (or from the user) and see section 7.

## 6. Alarm playbooks

All alarms are defined in `infra/terraform/modules/observability/main.tf`, evaluate on 5-minute
periods, use `treat_missing_data = notBreaching` and notify SNS `projects-api-<env>-alarms`.
Only `-lambda-errors`, `-api-5xx` and `-api-latency-p99` also send an OK notification; the
others go quiet without
telling you. Thresholds come from module variables with the defaults shown.

General first step for any alarm: open dashboard `projects-api-<env>` and set the time range to
the last 3 hours. Was there a deploy (`git log origin/main`, Lambda alias version)? Did traffic
change (`Count`)? Then follow the playbook. Escalate to the service owner when a check says
"escalate", when the mitigation would be a rollback you are not comfortable with, or when data
integrity is in question.

### `projects-api-<env>-lambda-errors`

`AWS/Lambda Errors`, `FunctionName=projects-api-<env>`, Sum >= 1 in one 5-minute period.

Meaning: at least one invocation ended in error: an unhandled exception that escaped the FastAPI
handlers, a timeout (10 s), out of memory (512 MB), or an import error at cold start. Ordinary
4xx/5xx returned by the app are **not** Lambda errors (the `_unhandled` handler catches
exceptions and returns a 500 problem), so this usually means something broke before or outside
FastAPI: bad package, missing environment variable, Mangum failure, or a timeout.

First checks:

1. Lambda log group, last 30 minutes:

   ```text
   fields @timestamp, @message
   | filter @message like /Task timed out|Runtime exited|Runtime.ImportModuleError|Unable to import|MemoryError|\[ERROR\]/
   | sort @timestamp desc
   | limit 50
   ```

2. Powertools error lines with the exception:

   ```text
   fields @timestamp, message, exception_name, exception, correlation_id, function_request_id
   | filter level = "ERROR"
   | sort @timestamp desc
   | limit 50
   ```

3. Memory and duration of the failing invocations:

   ```text
   filter @type = "REPORT"
   | stats max(@duration), max(@maxMemoryUsed) / 1000000 as maxMB, count(*) by bin(5m)
   ```

   Compare with 10,000 ms and 512 MB.

Likely causes: a just-deployed zip missing a dependency (import error on every cold start:
error count equals invocation count), a DynamoDB call hanging until the 10 s timeout (check
`-ddb-*` alarms too), a table permission or name change (`AccessDeniedException`,
`ResourceNotFoundException` in the log).

Mitigation: if it started with a deploy, roll back the alias (section 3). If it is a timeout on
DynamoDB, see `-ddb-throttled` and `-ddb-system-errors`. If it is a permission error, check the
last plan for IAM or table changes.

Escalate: errors continue after rollback, or every invocation fails (the API is down).

### `projects-api-<env>-lambda-throttles`

`AWS/Lambda Throttles`, `FunctionName=projects-api-<env>`, Sum >= 1 in one 5-minute period.

Meaning: the Lambda service refused invocations because the account's regional concurrency
limit (default 1,000, shared by every function in the account and region) was reached, or, if
`reserved_concurrency` has been set from its default `-1`, the function's own cap. API Gateway
turns a throttled invocation into a `5XX` (so `-api-5xx` often fires with it).

First checks:

1. `aws lambda get-account-settings --query AccountLimit` and the `ConcurrentExecutions`
   (Maximum) line on the dashboard widget "Lambda invocations, errors, throttles". The stage
   throttle is 50 req/s; with a 10 s timeout that alone can need up to 500 concurrent executions.
2. Access log: is it one key or everybody?

   ```text
   fields apiKeyId
   | stats count(*) as requests by apiKeyId
   | sort requests desc
   ```

3. Other functions in the account: `aws lambda list-functions --query 'Functions[].FunctionName'`
   and their invocations. A noisy neighbour exhausts the shared pool.

Likely causes: a traffic spike (legitimate or abusive) or another workload in the account
consuming the shared concurrency.

Mitigation: an abusive key can be disabled (section 4). For a shared-pool problem, request a
concurrency limit increase or set `reserved_concurrency` on the `lambda` module (this also
guarantees the function that many executions). If invocations are slow, fix the latency so
concurrency drops (see `-lambda-duration-p99`).

Escalate: throttles persist for more than two periods or another team's workload is the cause.

### `projects-api-<env>-lambda-duration-p99`

`AWS/Lambda Duration` p99, `FunctionName=projects-api-<env>`, > `lambda_p99_ms_threshold`
(2000 ms) in 3 consecutive 5-minute periods.

Meaning: the slowest 1% of invocations took over two seconds for fifteen minutes. On a
low-traffic stage a handful of cold starts can dominate the p99, so check the invocation count
before treating this as an incident.

First checks:

1. Cold start share:

   ```text
   filter @type = "REPORT"
   | stats count(*) as invocations, sum(strcontains(@message, "Init Duration")) as coldStarts,
           pct(@duration, 99) as p99, max(@initDuration) as maxInit by bin(5m)
   ```

   If `coldStarts` is close to `invocations`, the p99 is cold-start time (typically 1 to 2 s for
   FastAPI + Pydantic on 512 MB), not a regression.
2. Warm-invocation latency from the `request completed` lines:

   ```text
   filter ispresent(duration_ms)
   | stats pct(duration_ms, 50), pct(duration_ms, 99), count(*) by route, method
   ```

3. DynamoDB side: dashboard widget "DynamoDB consumed capacity and errors" and the
   `SuccessfulRequestLatency` metric for the table (CloudWatch > Metrics > DynamoDB > Table
   Metrics > `projects-api-<env>`). boto3 is configured with adaptive retries (up to 5 attempts),
   so throttling shows up as latency before it shows up as errors.

Likely causes: cold starts under bursty low traffic; DynamoDB throttling or elevated latency;
a deploy that added heavy imports or synchronous work.

Mitigation: if it is cold starts and traffic matters, raise `lambda_memory_mb` (more CPU) or
consider provisioned concurrency (not defined today). If it is DynamoDB, follow `-ddb-throttled`.
If it started with a deploy, roll back (section 3).

Escalate: sustained p99 above the 10 s timeout risk (`-lambda-errors` firing with `Task timed
out`), or latency attributable to DynamoDB that you cannot explain.

### `projects-api-<env>-api-5xx`

`AWS/ApiGateway 5XXError`, `ApiName=projects-api-<env>`, `Stage=live`, Sum >= 1 in one
5-minute period.

Meaning: the gateway returned at least one 5xx: either the application returned a 500 problem
(unhandled exception caught by `_unhandled`), or the integration itself failed (Lambda
throttled, timed out, permission denied, or returned a malformed response -> `502`/`504`).

First checks:

1. Access log:

   ```text
   fields @timestamp, requestId, httpMethod, path, status, integrationMs, errorMessage
   | filter status like /^5/
   | sort @timestamp desc
   | limit 50
   ```

   `status=500` with `errorMessage` empty means the app returned a problem: continue in the
   Lambda log with that `requestId` (section 5). `502` or `504` with an `errorMessage` means
   Lambda never answered properly: check `-lambda-errors` and `-lambda-throttles`.
2. Lambda log, same window, unhandled exceptions:

   ```text
   fields @timestamp, message, exception_name, exception, correlation_id
   | filter message = "Unhandled error"
   | sort @timestamp desc
   ```

3. The Lambda invoke permission if this began after an infra change:
   `aws lambda get-policy --function-name projects-api-dev --qualifier live` should contain
   `AllowAPIGatewayInvoke` with the API's execution ARN.

Likely causes: a code bug (look at `exception_name`), DynamoDB errors surfacing as unhandled
`ClientError`s, Lambda throttling, or a broken deploy.

Mitigation: roll back the alias if it began with a deploy. Otherwise fix forward. If a single
malformed request pattern triggers it, tell the caller and open a bug with the `requestId`.

Escalate: 5xx on `GET /health` (the whole stack is down) or more than a handful per period.

### `projects-api-<env>-api-4xx-ratio`

Metric math `IF(count > 20, errors / count, 0)` over `AWS/ApiGateway 4XXError` and `Count`
(`ApiName=projects-api-<env>`, `Stage=live`), > `api_4xx_ratio_threshold` (0.5) in 3
consecutive 5-minute periods. Periods with 20 or fewer requests evaluate to 0.

Meaning: for fifteen minutes more than half of all requests were rejected with 4xx. A few 4xx
are normal (validation errors, duplicate names, unknown ids); a majority means a broken or
misconfigured client, an unauthorised scanner, or a key that has been throttled or disabled.

First checks:

1. Which statuses and paths:

   ```text
   fields status, path
   | filter status like /^4/
   | stats count(*) as n by status, path
   | sort n desc
   ```

   `403` = missing or invalid key (gateway); `429` = per-key or stage throttle (gateway);
   `400`/`404`/`409` = application responses.
2. Who:

   ```text
   fields apiKeyId, ip, userAgent
   | filter status like /^4/
   | stats count(*) as n by apiKeyId, ip, userAgent
   | sort n desc
   | limit 20
   ```

   An empty `apiKeyId` with `403` is an unauthenticated caller (scanner or misconfigured
   client). One key with many `429`s has exceeded 10 req/s or its 10,000/month quota
   (`get-usage`, section 4).
3. Business metric `ProjectNameConflicts` on the dashboard: a burst of `409`s
   from one key is usually a retry loop.

Likely causes: a client retrying a failing request in a loop; a disabled or rotated key still in
use; an internet scanner probing the endpoint; a legitimate client exceeding its quota.

Mitigation: contact the key's owner; disable the key if it is clearly abusive (section 4). For
unauthenticated scanning the WAF in [#23](https://github.com/jameslevine/projects-api/issues/23)
is the eventual answer; today the gateway already rejects these before Lambda, so cost impact is
limited to API Gateway requests and access-log lines.

Escalate: sustained abuse from many IPs, or 4xx caused by a server-side change (for example a
validation rule tightened by a deploy, visible as `400` from previously good clients).

### `projects-api-<env>-api-latency-p99`

`AWS/ApiGateway Latency` p99, `ApiName=projects-api-<env>`, `Stage=live`, >
`api_p99_ms_threshold` (1500 ms; settable per environment in `envs/<env>/variables.tf`) in 3 of 3
consecutive 5-minute periods (`datapoints_to_alarm = 3`).

Meaning: end-to-end latency as seen at the gateway (including Lambda cold starts and gateway
overhead) is high for the slowest 1% of requests. It usually fires together with
`-lambda-duration-p99`; if it fires alone, the time is being spent outside Lambda.

First checks:

1. Gateway overhead versus integration time:

   ```text
   fields latencyMs, integrationMs
   | stats pct(latencyMs, 99) as p99Total, pct(integrationMs, 99) as p99Lambda, count(*) by bin(5m)
   ```

   A large gap between the two is gateway-side (rare; check the AWS Health Dashboard for
   API Gateway in eu-west-2).
2. Follow the `-lambda-duration-p99` checks for the Lambda share.
3. Dashboard widget "API latency (ms)" p50 versus p99: a p50 increase is systemic; a p99-only
   increase is cold starts or a few slow requests.

Mitigation and escalation: as for `-lambda-duration-p99`.

### `projects-api-<env>-ddb-system-errors`

Metric math: `SUM` of `AWS/DynamoDB SystemErrors` (Sum) over one series per operation in
`var.ddb_operations` (`GetItem`, `Query`, `TransactWriteItems`, `DeleteItem`), each with
dimensions `TableName=projects-api-<env>` and `Operation=<op>`; >= 1 in one 5-minute period.
`SystemErrors` is only published per `TableName` + `Operation`, which is why the alarm sums
per-operation series rather than reading a table-level metric.

Meaning: DynamoDB itself returned a 5xx (`InternalServerError`, `ServiceUnavailable`) for a
request against the table. This is an AWS-side fault, not a bug in the API; boto3 retries these
(adaptive mode, up to 5 attempts) so a single system error often produces only extra latency.

First checks:

1. Which operation: open the alarm in the console and expand the metric graph, or CloudWatch >
   Metrics > DynamoDB > Table Operation Metrics > `projects-api-<env>`, `SystemErrors` and
   `SuccessfulRequestLatency` per `Operation`. The dashboard widget "DynamoDB consumed capacity
   and errors" plots the same total via a `SEARCH` over every operation. Then check the AWS
   Health Dashboard for DynamoDB in eu-west-2.
2. Did anything reach the client? Access log `status like /^5/` (as in `-api-5xx`) and Lambda
   log:

   ```text
   fields @timestamp, message, exception_name, exception
   | filter exception like /InternalServerError|ServiceUnavailable/
   ```

3. `aws dynamodb describe-table --table-name projects-api-dev --query 'Table.{Status:TableStatus,GSI:GlobalSecondaryIndexes[].IndexStatus}'`
   should be `ACTIVE` everywhere.

Maintenance: the alarm only covers the operations listed in `ddb_operations`
(`infra/terraform/modules/observability/variables.tf`). When the repository starts calling a new
DynamoDB operation (for example `UpdateItem` or `BatchWriteItem`), add it to that list, or its
system errors will not be alarmed on. The dashboard `SEARCH` needs no change.

Likely causes: a DynamoDB service event.

Mitigation: none on our side beyond retries. If a `TransactWriteItems` failed mid-way it is
atomic, so no half-written project exists. Re-run the failing client requests.

Escalate: errors persist beyond one period, or coincide with a Health Dashboard event, in which
case open an AWS Support case.

### `projects-api-<env>-ddb-throttled`

Metric math: `AWS/DynamoDB ReadThrottleEvents + WriteThrottleEvents` (Sum, table level,
`TableName=projects-api-<env>`) >= 1 in one 5-minute period. These count throttled read and
write events on the base table; GSI throttling is published separately (below).

Meaning: DynamoDB rejected requests with `ProvisionedThroughputExceededException` (the same
error name is used for on-demand tables). The table is on-demand, so this means either a
traffic burst more than double the previous 30-minute peak, a single partition exceeding its
hard limit (3,000 RCU / 1,000 WCU), or throttling on `GSI1` (one owner with a very large number
of projects being listed). boto3 retries with backoff, so clients see latency first, then 500s
if all attempts fail.

First checks:

1. Which side and which index: open the alarm graph to see whether `reads` or `writes` breached,
   then CloudWatch > Metrics > DynamoDB, `ReadThrottleEvents` and `WriteThrottleEvents` for
   `GlobalSecondaryIndexName=GSI1` (not alarmed on; the dashboard widget shows the table-level
   pair) and `ThrottledRequests` by `Operation` (`TransactWriteItems`, `GetItem`, `Query`) to
   see which call is affected.
2. Traffic shape in the access log:

   ```text
   fields httpMethod, path, apiKeyId
   | stats count(*) as n by bin(1m), httpMethod, apiKeyId
   | sort n desc
   ```

   Many `POST /v1/projects` from one key is a write burst; many `GET /v1/projects` is a GSI1
   read burst on `OWNER#<keyId>`.
3. Lambda log for the exception:

   ```text
   filter exception like /ProvisionedThroughputExceededException|ThrottlingException/
   | stats count(*) by bin(5m)
   ```

Likely causes: a load test or retry loop from one key; an owner partition in GSI1 with very
many projects; a sudden traffic step after a long quiet period (on-demand needs time to scale).

Mitigation: per-key throttling (10 req/s) already bounds one key; disable an abusive key
(section 4). If the traffic is legitimate and sustained, on-demand adapts within minutes; if it
keeps throttling, switch the table to provisioned capacity with autoscaling (Terraform change).

Escalate: throttling causing 5xx for more than one period, or a hot-partition pattern that
needs a data-model change.

### Budget notifications: `projects-api-<env>-monthly`

Not a CloudWatch alarm: AWS Budgets sends to the same SNS topic (and `alarm_email`) when the
**forecast** month-end spend exceeds 80% of `monthly_budget_usd` (default USD 20) and when
**actual** spend exceeds 100%. The filter is the cost allocation tag `Project=projects-api`.

First checks: Cost Explorer filtered by that tag, grouped by service (section 8). The usual
suspects are CloudWatch (log ingestion from a traffic burst or `LOG_LEVEL=DEBUG`), API Gateway
requests from a scanner or retry loop, and X-Ray traces.

Mitigation: stop the traffic source (disable the key, section 4), reduce log volume
(`LOG_LEVEL`, sample rate is already 1 in dev), and check for resources that should not exist
(`aws resourcegroupstaggingapi get-resources --tag-filters Key=Project,Values=projects-api`).

Escalate: actual spend exceeds the budget and you cannot identify the driver.

## 7. DynamoDB

Table `projects-api-<env>`, keys `PK`/`SK`, GSI `GSI1` (`GSI1PK`/`GSI1SK`, projection `ALL`),
on-demand, PITR enabled, AWS-owned encryption key, deletion protection only in `prod`. Items
(from [architecture.md](architecture.md#data-model)):

| Item | `PK` | `SK` | Notes |
|---|---|---|---|
| Project record | `PROJECT#<projectId>` | `META` | `ownerId`, `name`, `nameKey`, `type`, `status`, `createdAt`, `updatedAt`, `GSI1PK=OWNER#<ownerId>`, `GSI1SK=PROJECT#<createdAt>#<projectId>` |
| Name reservation | `NAME#<nameKey>` | `RESERVATION` | `projectId`, `ownerId`, `createdAt`; no GSI keys |

`nameKey` is the name trimmed, with internal whitespace collapsed to one space, lower-cased
(`domain/validation.py`). `My  Agent` -> `my agent`. The two items are written in one
`TransactWriteItems` and a project is only consistent when both exist and agree on `projectId`.

### Inspect a project and its reservation

```bash
TABLE=projects-api-dev

# The project record
aws dynamodb get-item --table-name "${TABLE}" --consistent-read \
  --key '{"PK":{"S":"PROJECT#prj_8ead2ca56357488283af38744fe08a65"},"SK":{"S":"META"}}'

# Its name reservation (use the nameKey attribute from the record)
aws dynamodb get-item --table-name "${TABLE}" --consistent-read \
  --key '{"PK":{"S":"NAME#my-first-agent"},"SK":{"S":"RESERVATION"}}'

# Everything one owner (API key id) has, newest first, as the list endpoint sees it
aws dynamodb query --table-name "${TABLE}" --index-name GSI1 --no-scan-index-forward \
  --key-condition-expression 'GSI1PK = :pk AND begins_with(GSI1SK, :p)' \
  --expression-attribute-values '{":pk":{"S":"OWNER#<keyId>"},":p":{"S":"PROJECT#"}}'
```

A `409` for a name that "does not exist" means the reservation exists without a visible project:
fetch the reservation, take its `projectId`, and fetch the record. If the record is missing the
reservation is an orphan (should not happen with the transaction; if it does, capture both
items and escalate before deleting anything).

### Point-in-time restore

PITR restores to a **new** table; it never overwrites the source. Restores take minutes to tens
of minutes and are billed by restored size (tiny here). The restored table has the base table's
data and indexes but **not** its PITR setting, tags, deletion protection, or IAM grants, and the
Lambda role can only reach the original table ARN.

```bash
SRC=projects-api-dev
DST=projects-api-dev-restore-$(date +%Y%m%d%H%M)

aws dynamodb describe-continuous-backups --table-name "${SRC}" \
  --query 'ContinuousBackupsDescription.PointInTimeRecoveryDescription'   # EarliestRestorableDateTime, LatestRestorableDateTime

# CHANGES AWS (creates a table). Pick one of the two time options.
aws dynamodb restore-table-to-point-in-time --source-table-name "${SRC}" --target-table-name "${DST}" \
  --restore-date-time 2026-09-23T10:15:00Z
# or: --use-latest-restorable-time

aws dynamodb wait table-exists --table-name "${DST}"
aws dynamodb describe-table --table-name "${DST}" --query 'Table.{Status:TableStatus,Items:ItemCount}'
```

Then decide how to use it. There are two options; prefer the first.

1. **Copy items back into the original table** (surgical: a deleted or corrupted project). For
   each project, put **both** items, the `PROJECT#.../META` record and the `NAME#.../RESERVATION`,
   and use `--condition-expression 'attribute_not_exists(PK)'` so you never overwrite something
   written after the restore point. If the condition fails on the reservation, the name has since
   been taken by another project: stop and decide with the owner which one wins; do not force it.

   ```bash
   aws dynamodb get-item --table-name "${DST}" --key '{"PK":{"S":"PROJECT#<id>"},"SK":{"S":"META"}}' --query Item > /tmp/meta.json
   aws dynamodb get-item --table-name "${DST}" --key '{"PK":{"S":"NAME#<nameKey>"},"SK":{"S":"RESERVATION"}}' --query Item > /tmp/res.json
   # CHANGES AWS
   aws dynamodb put-item --table-name "${SRC}" --item file:///tmp/res.json  --condition-expression 'attribute_not_exists(PK)'
   aws dynamodb put-item --table-name "${SRC}" --item file:///tmp/meta.json --condition-expression 'attribute_not_exists(PK)'
   ```

2. **Swap the application onto the restored table** (whole-table loss). Requires a Terraform
   change (the table module would need to import or adopt the restored table, and the Lambda IAM
   policy and `TABLE_NAME` point at the table ARN/name), plus re-enabling PITR and deletion
   protection on the new table. Treat as an incident with the service owner; do not do this
   ad hoc.

Name reservations when restoring: because a name is unique across all owners and the two items
live in different partitions, any restore that is not the whole table can produce one of two
inconsistent states. Check for both after copying:

- A project record without a reservation: the name can be taken again by someone else, and a
  later delete ([#25](https://github.com/jameslevine/projects-api/issues/25)) would release the
  wrong reservation. Fix by putting the reservation (conditionally, as above).
- A reservation without a project record: the name is blocked for everyone. Fix by deleting the
  reservation **only** after confirming no `PROJECT#<projectId>/META` exists for its
  `projectId`.

Consistency sweep over the restored (or live) table:

```bash
# Every reservation with its projectId, and every project with its nameKey
aws dynamodb scan --table-name "${TABLE}" --filter-expression 'entity = :e' \
  --expression-attribute-values '{":e":{"S":"NAME_RESERVATION"}}' \
  --projection-expression 'PK, projectId' --output json > /tmp/reservations.json
aws dynamodb scan --table-name "${TABLE}" --filter-expression 'entity = :e' \
  --expression-attribute-values '{":e":{"S":"PROJECT"}}' \
  --projection-expression 'PK, nameKey, projectId' --output json > /tmp/projects.json
```

Compare the two sets (each `PROJECT#<projectId>` should have exactly one `NAME#<nameKey>` whose
`projectId` matches, and vice versa). Delete the restored table when finished
(`aws dynamodb delete-table --table-name "${DST}"`, CHANGES AWS) so it does not keep costing
storage.

## 8. Monthly cost review checklist

Everything the stack creates carries `Project=projects-api` (provider `default_tags` plus module
tags; API keys created by `scripts/create_api_key.sh` are tagged too). The budget and Cost
Explorer both filter on that tag, so **`Project` must be activated as a cost allocation tag**
once per account; until then both show nothing. The one-time command, its permissions and the
up-to-24-hour delay are documented in [README, Deploy step 6](../README.md#deploy); to check
whether it has been done:

```bash
aws ce list-cost-allocation-tags --tag-keys Project --type UserDefined
# "Status": "Active" is what you want; "Inactive" means run the README step.
```

- [ ] Cost Explorer, last full month, filter Tag `Project = projects-api`, group by Service:

  ```bash
  aws ce get-cost-and-usage --time-period Start=2026-09-01,End=2026-10-01 --granularity MONTHLY \
    --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE \
    --filter '{"Tags":{"Key":"Project","Values":["projects-api"]}}'
  ```

- [ ] Compare with expected drivers, roughly in this order for a low-traffic API:
  - **API Gateway REST**: per request (every call, including gateway-rejected 403/429s).
  - **CloudWatch**: log ingestion and storage for both log groups (14-day retention), alarms
    (8; the two p99 alarms use percentile statistics, and the 4XX ratio, DynamoDB system-errors
    and DynamoDB throttled alarms are metric-math alarms billed per metric evaluated, 3, 4 and 2
    respectively, all costing more than a plain alarm), custom metrics in
    `ProjectsApi`, dashboard (first three per account are free).
  - **Lambda**: requests and GB-seconds at 512 MB arm64; cold starts count.
  - **DynamoDB on-demand**: read/write request units (a create is a 2-item transaction, so
    roughly 4 WRU), storage, PITR storage (billed per GB-month of table size).
  - **X-Ray**: traces recorded and retrieved (both the stage and the function sample).
  - **S3 / DynamoDB (bootstrap)**: state bucket and lock table, negligible.
- [ ] Anything else under the tag (`aws resourcegroupstaggingapi get-resources --tag-filters
  Key=Project,Values=projects-api --query 'ResourceTagMappingList[].ResourceARN'`) that is not in
  the table in section 1: restored DynamoDB tables from section 7, forgotten test resources.
- [ ] Budget state: `aws budgets describe-budget --account-id <id> --budget-name projects-api-dev-monthly`
  and whether `monthly_budget_usd` (default 20, set in `infra/terraform/envs/dev/dev.tfvars`)
  still reflects expected spend. Raise it deliberately rather than muting notifications.
- [ ] Log volume: `IncomingBytes` per log group over the month. If Lambda logs dominate, check
  `LOG_LEVEL` (default `INFO`) and `POWERTOOLS_LOGGER_SAMPLE_RATE` (`1` outside prod, `0.05` in
  prod). Retention is `log_retention_days` (default 14) in both `lambda_api` and
  `api_gateway_rest` modules; it is not exposed at the environment root, so changing it is a
  module edit.
- [ ] Traffic sanity: total `Count` versus keys in use (`get-api-keys --name-query
  projects-api-dev-`); disable keys that no longer have an owner (section 4).
- [ ] Unused published Lambda versions: they cost nothing while total stored code is small, but
  `list-versions-by-function` growing past a few dozen is a sign that clean-up should be added
  to `scripts/rollback.sh`.

## 9. Known limitations and open items

- The smoke test has never been run against a deployed stage; the whole deploy path is
  validated only by `terraform validate` and CI: [#16](https://github.com/jameslevine/projects-api/issues/16).
- Log lines from versions deployed before request correlation shipped
  ([#21](https://github.com/jameslevine/projects-api/issues/21), closed) have no `correlation_id` and
  quoted the Lambda id as `requestId`; trace those via the access-log timestamp join (section 5).
- The DynamoDB system-errors alarm covers only the operations in `ddb_operations` (section 6);
  GSI1 throttling is visible in the console but has no alarm. Both came out of the alarm review
  in [#20](https://github.com/jameslevine/projects-api/issues/20) (closed).
- WAF is optional and off by default (`enable_waf`, [#23](https://github.com/jameslevine/projects-api/issues/23),
  closed); without it the gateway's own throttling and key check are the only protection
  against scanning.
- No production environment; `dev` has deletion protection off and no alarm email by default:
  [#28](https://github.com/jameslevine/projects-api/issues/28).
- No delete endpoint, so orphaned projects and reservations (disabled keys, restores) can only
  be cleaned up in DynamoDB directly: [#25](https://github.com/jameslevine/projects-api/issues/25).
- API Gateway deployment rollback is normally impossible because Terraform destroys the
  replaced deployment (section 3).
