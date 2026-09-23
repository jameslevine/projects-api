# Provisioner: consumes the projects table's DynamoDB stream and moves new projects through
# CREATED -> PROVISIONING -> READY | FAILED (src/projects_provisioner). It is deployed from the
# same zip as the API with a different handler.

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

# Batches that exhaust their retries land here (event source mapping on_failure destination).
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-dlq"
  message_retention_seconds = 1209600 # 14 days, the SQS maximum
  sqs_managed_sse_enabled   = true
  tags                      = var.tags
}

# Least privilege: the two status writes, the stream the mapping polls, and the DLQ.
data "aws_iam_policy_document" "this" {
  statement {
    sid       = "ProjectStatusTransitions"
    actions   = ["dynamodb:UpdateItem"]
    resources = [var.table_arn]
  }

  statement {
    sid = "ReadTableStream"
    actions = [
      "dynamodb:DescribeStream",
      "dynamodb:GetRecords",
      "dynamodb:GetShardIterator",
      "dynamodb:ListStreams",
    ]
    resources = [var.stream_arn]
  }

  statement {
    sid       = "FailedBatchesToDlq"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
}

resource "aws_iam_role_policy" "this" {
  name   = "${var.name}-policy"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.this.json
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_lambda_function" "this" {
  function_name    = var.name
  role             = aws_iam_role.this.arn
  handler          = "projects_provisioner.handler.handler"
  runtime          = "python3.12"
  architectures    = ["arm64"]
  filename         = var.zip_path
  source_code_hash = filebase64sha256(var.zip_path)
  memory_size      = var.memory_mb
  timeout          = var.timeout_seconds

  reserved_concurrent_executions = var.reserved_concurrency

  environment {
    variables = {
      ENV                                = var.environment
      TABLE_NAME                         = var.table_name
      LOG_LEVEL                          = var.log_level
      SERVICE_NAME                       = "projects-provisioner"
      POWERTOOLS_SERVICE_NAME            = "projects-provisioner"
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

# Only INSERTs of PROJECT items reach the function; everything else is dropped by the filter
# before it is billed. Partial batch responses let one bad record fail without the whole batch.
resource "aws_lambda_event_source_mapping" "stream" {
  event_source_arn                   = var.stream_arn
  function_name                      = aws_lambda_function.this.arn
  starting_position                  = "LATEST"
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  bisect_batch_on_function_error     = true
  maximum_retry_attempts             = 3
  function_response_types            = ["ReportBatchItemFailures"]

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.dlq.arn
    }
  }

  filter_criteria {
    filter {
      pattern = jsonencode({
        eventName = ["INSERT"]
        dynamodb = {
          NewImage = {
            entity = { S = ["PROJECT"] }
          }
        }
      })
    }
  }

  # Lambda checks the role can read the stream when the mapping is created.
  depends_on = [aws_iam_role_policy.this]
}

resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${var.name}-dlq-messages"
  alarm_description   = "Provisioner batches exhausted their retries and are waiting in the DLQ; inspect and redrive"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
  ok_actions          = [var.alarm_topic_arn]
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.name}-lambda-errors"
  alarm_description   = "Provisioner Lambda reported invocation errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.this.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [var.alarm_topic_arn]
  ok_actions          = [var.alarm_topic_arn]
  tags                = var.tags
}
