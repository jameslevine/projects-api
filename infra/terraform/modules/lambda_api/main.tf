data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "xray" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# Least privilege: only the actions the repository uses, only on this table and its indexes.
data "aws_iam_policy_document" "table" {
  statement {
    sid = "ProjectsTableAccess"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:TransactWriteItems",
      "dynamodb:ConditionCheckItem",
    ]
    resources = [var.table_arn, "${var.table_arn}/index/*"]
  }
}

resource "aws_iam_role_policy" "table" {
  name   = "${var.name}-table"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.table.json
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_lambda_function" "this" {
  function_name    = var.name
  role             = aws_iam_role.this.arn
  handler          = "projects_api.main.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = var.zip_path
  source_code_hash = filebase64sha256(var.zip_path)
  memory_size      = var.memory_mb
  timeout          = var.timeout_seconds
  publish          = true

  reserved_concurrent_executions = var.reserved_concurrency

  environment {
    variables = {
      ENV                                = var.environment
      TABLE_NAME                         = var.table_name
      LOG_LEVEL                          = var.log_level
      POWERTOOLS_SERVICE_NAME            = "projects-api"
      POWERTOOLS_METRICS_NAMESPACE       = "ProjectsApi"
      POWERTOOLS_LOGGER_LOG_EVENT        = "false"
      POWERTOOLS_LOGGER_SAMPLE_RATE      = var.environment == "prod" ? "0.05" : "1"
      PYTHONDONTWRITEBYTECODE            = "1"
      POWERTOOLS_TRACER_CAPTURE_ERROR    = "true"
      POWERTOOLS_TRACER_CAPTURE_RESPONSE = "false"
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.this, aws_iam_role_policy_attachment.basic]
  tags       = var.tags
}

# Stable alias for API Gateway to target. Rollback = repoint alias to a previous version.
resource "aws_lambda_alias" "live" {
  name             = "live"
  function_name    = aws_lambda_function.this.function_name
  function_version = aws_lambda_function.this.version
}
