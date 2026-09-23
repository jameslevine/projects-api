# REST API (not HTTP API) because API keys and usage plans are only supported here.

resource "aws_api_gateway_rest_api" "this" {
  name        = var.name
  description = "Projects API (${var.environment})"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  # Reject oversized/undeclared payloads at the edge.
  minimum_compression_size = -1
  tags                     = var.tags
}

# GET /health : public liveness probe, no API key.
resource "aws_api_gateway_resource" "health" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "health"
}

resource "aws_api_gateway_method" "health_get" {
  rest_api_id      = aws_api_gateway_rest_api.this.id
  resource_id      = aws_api_gateway_resource.health.id
  http_method      = "GET"
  authorization    = "NONE"
  api_key_required = false
}

resource "aws_api_gateway_integration" "health_get" {
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = aws_api_gateway_resource.health.id
  http_method             = aws_api_gateway_method.health_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.lambda_invoke_arn
}

# ANY /{proxy+} : everything else, API key required.
resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_request_validator" "params" {
  name                        = "validate-parameters"
  rest_api_id                 = aws_api_gateway_rest_api.this.id
  validate_request_parameters = true
  validate_request_body       = false # body validation is owned by FastAPI/Pydantic
}

resource "aws_api_gateway_method" "proxy_any" {
  rest_api_id          = aws_api_gateway_rest_api.this.id
  resource_id          = aws_api_gateway_resource.proxy.id
  http_method          = "ANY"
  authorization        = "NONE"
  api_key_required     = true
  request_validator_id = aws_api_gateway_request_validator.params.id

  request_parameters = {
    "method.request.path.proxy" = true
  }
}

resource "aws_api_gateway_integration" "proxy_any" {
  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy_any.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.lambda_invoke_arn
}

# Gateway responses as problem+json so clients see one error shape even for
# errors that never reach Lambda (missing/invalid key, throttling).
resource "aws_api_gateway_gateway_response" "unauthorized" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  response_type = "UNAUTHORIZED"
  status_code   = "401"
  response_templates = {
    "application/json" = jsonencode({
      type   = "https://projects-api.example/problems/http-401"
      title  = "Unauthorized"
      status = 401
      detail = "A valid x-api-key header is required."
    })
  }
  response_parameters = {
    "gatewayresponse.header.Content-Type" = "'application/problem+json'"
  }
}

resource "aws_api_gateway_gateway_response" "invalid_api_key" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  response_type = "INVALID_API_KEY"
  status_code   = "403"
  response_templates = {
    "application/json" = jsonencode({
      type   = "https://projects-api.example/problems/http-403"
      title  = "Forbidden"
      status = 403
      detail = "The x-api-key header is missing or invalid."
    })
  }
  response_parameters = {
    "gatewayresponse.header.Content-Type" = "'application/problem+json'"
  }
}

resource "aws_api_gateway_gateway_response" "throttled" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  response_type = "THROTTLED"
  status_code   = "429"
  response_templates = {
    "application/json" = jsonencode({
      type   = "https://projects-api.example/problems/http-429"
      title  = "Too many requests"
      status = 429
      detail = "Rate or quota limit exceeded for this API key."
    })
  }
  response_parameters = {
    "gatewayresponse.header.Content-Type" = "'application/problem+json'"
  }
}

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  # Redeploy whenever any of the API definition changes.
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.health.id,
      aws_api_gateway_method.health_get.id,
      aws_api_gateway_integration.health_get.id,
      aws_api_gateway_resource.proxy.id,
      aws_api_gateway_method.proxy_any.id,
      aws_api_gateway_integration.proxy_any.id,
      aws_api_gateway_request_validator.params.id,
      aws_api_gateway_gateway_response.unauthorized.id,
      aws_api_gateway_gateway_response.invalid_api_key.id,
      aws_api_gateway_gateway_response.throttled.id,
      var.lambda_invoke_arn,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_cloudwatch_log_group" "access" {
  name              = "/aws/apigateway/${var.name}/access"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id          = aws_api_gateway_rest_api.this.id
  deployment_id        = aws_api_gateway_deployment.this.id
  stage_name           = var.stage_name
  xray_tracing_enabled = true
  tags                 = var.tags

  # Structured access log without request/response bodies.
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      apiKeyId       = "$context.identity.apiKeyId"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      path           = "$context.path"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      latencyMs      = "$context.responseLatency"
      integrationMs  = "$context.integrationLatency"
      errorMessage   = "$context.error.message"
      userAgent      = "$context.identity.userAgent"
    })
  }

  depends_on = [aws_api_gateway_account.this]
}

resource "aws_api_gateway_method_settings" "all" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  stage_name  = aws_api_gateway_stage.this.stage_name
  method_path = "*/*"

  settings {
    metrics_enabled        = true
    logging_level          = "ERROR"
    data_trace_enabled     = false # never log bodies
    throttling_burst_limit = var.stage_throttle_burst
    throttling_rate_limit  = var.stage_throttle_rate
  }
}

# Account-level role that lets API Gateway write to CloudWatch Logs. One per account/region.
data "aws_iam_policy_document" "apigw_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cloudwatch" {
  count              = var.manage_account_cloudwatch_role ? 1 : 0
  name               = "${var.name}-apigw-cloudwatch"
  assume_role_policy = data.aws_iam_policy_document.apigw_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "cloudwatch" {
  count      = var.manage_account_cloudwatch_role ? 1 : 0
  role       = aws_iam_role.cloudwatch[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

resource "aws_api_gateway_account" "this" {
  cloudwatch_role_arn = var.manage_account_cloudwatch_role ? aws_iam_role.cloudwatch[0].arn : null
}

# Usage plan: per-key throttling and a monthly quota. Every user key is attached to it.
resource "aws_api_gateway_usage_plan" "default" {
  name        = "${var.name}-default"
  description = "Default plan for project owners"
  tags        = var.tags

  api_stages {
    api_id = aws_api_gateway_rest_api.this.id
    stage  = aws_api_gateway_stage.this.stage_name
  }

  throttle_settings {
    burst_limit = var.key_throttle_burst
    rate_limit  = var.key_throttle_rate
  }

  quota_settings {
    limit  = var.key_monthly_quota
    period = "MONTH"
  }
}

# One key so the stage is usable straight after apply. Further keys: scripts/create_api_key.sh
resource "aws_api_gateway_api_key" "demo" {
  name        = "${var.name}-demo"
  description = "Initial demo user key. Rotate or disable once real users are onboarded."
  enabled     = true
  tags        = var.tags
}

resource "aws_api_gateway_usage_plan_key" "demo" {
  key_id        = aws_api_gateway_api_key.demo.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.default.id
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  qualifier     = var.lambda_alias_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/*/*"
}
