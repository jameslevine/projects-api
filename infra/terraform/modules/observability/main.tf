resource "aws_sns_topic" "alarms" {
  name = "${var.name}-alarms"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == null ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  alarm_actions = [aws_sns_topic.alarms.arn]
  lambda_dims   = { FunctionName = var.lambda_function_name }
  api_dims      = { ApiName = var.api_name, Stage = var.api_stage }
  table_dims    = { TableName = var.table_name }
}

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.name}-lambda-errors"
  alarm_description   = "Lambda reported invocation errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = local.lambda_dims
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  alarm_name          = "${var.name}-lambda-throttles"
  alarm_description   = "Lambda invocations were throttled"
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = local.lambda_dims
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_duration_p99" {
  alarm_name          = "${var.name}-lambda-duration-p99"
  alarm_description   = "Lambda p99 duration is high"
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  dimensions          = local.lambda_dims
  extended_statistic  = "p99"
  period              = 300
  evaluation_periods  = 3
  threshold           = var.lambda_p99_ms_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = var.tags
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.name}-api-5xx"
  alarm_description   = "API Gateway returned 5XX responses"
  namespace           = "AWS/ApiGateway"
  metric_name         = "5XXError"
  dimensions          = local.api_dims
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = var.tags
}

# 4XX ratio rather than count: a burst of validation errors or bad keys may indicate abuse
# or a broken client, but a handful is normal.
resource "aws_cloudwatch_metric_alarm" "api_4xx_ratio" {
  alarm_name          = "${var.name}-api-4xx-ratio"
  alarm_description   = "More than ${var.api_4xx_ratio_threshold * 100}% of requests are 4XX"
  evaluation_periods  = 3
  threshold           = var.api_4xx_ratio_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = var.tags

  metric_query {
    id          = "ratio"
    expression  = "IF(count > 20, errors / count, 0)"
    label       = "4XX ratio"
    return_data = true
  }
  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/ApiGateway"
      metric_name = "4XXError"
      dimensions  = local.api_dims
      period      = 300
      stat        = "Sum"
    }
  }
  metric_query {
    id = "count"
    metric {
      namespace   = "AWS/ApiGateway"
      metric_name = "Count"
      dimensions  = local.api_dims
      period      = 300
      stat        = "Sum"
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "api_latency_p99" {
  alarm_name          = "${var.name}-api-latency-p99"
  alarm_description   = "API Gateway p99 latency is high"
  namespace           = "AWS/ApiGateway"
  metric_name         = "Latency"
  dimensions          = local.api_dims
  extended_statistic  = "p99"
  period              = 300
  evaluation_periods  = 3
  datapoints_to_alarm = 3
  threshold           = var.api_p99_ms_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = var.tags
}

# AWS/DynamoDB SystemErrors has dimensions TableName + Operation only; there is no TableName-only
# series, so an alarm on {TableName} never receives data. Sum one series per operation we issue.
resource "aws_cloudwatch_metric_alarm" "ddb_system_errors" {
  alarm_name          = "${var.name}-ddb-system-errors"
  alarm_description   = "DynamoDB returned system errors (any operation)"
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = var.tags

  metric_query {
    id          = "total"
    expression  = "SUM([${join(", ", [for op in var.ddb_operations : "sys_${lower(op)}"])}])"
    label       = "SystemErrors (all operations)"
    return_data = true
  }

  dynamic "metric_query" {
    for_each = toset(var.ddb_operations)
    content {
      id = "sys_${lower(metric_query.value)}"
      metric {
        namespace   = "AWS/DynamoDB"
        metric_name = "SystemErrors"
        dimensions  = merge(local.table_dims, { Operation = metric_query.value })
        period      = 300
        stat        = "Sum"
      }
    }
  }
}

# ThrottledRequests is also per TableName + Operation. ReadThrottleEvents and WriteThrottleEvents
# are the table-level throttle metrics, so alarm on their sum.
resource "aws_cloudwatch_metric_alarm" "ddb_throttled" {
  alarm_name          = "${var.name}-ddb-throttled"
  alarm_description   = "DynamoDB read or write requests were throttled"
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
  tags                = var.tags

  metric_query {
    id          = "throttles"
    expression  = "reads + writes"
    label       = "Throttle events (read + write)"
    return_data = true
  }
  metric_query {
    id = "reads"
    metric {
      namespace   = "AWS/DynamoDB"
      metric_name = "ReadThrottleEvents"
      dimensions  = local.table_dims
      period      = 300
      stat        = "Sum"
    }
  }
  metric_query {
    id = "writes"
    metric {
      namespace   = "AWS/DynamoDB"
      metric_name = "WriteThrottleEvents"
      dimensions  = local.table_dims
      period      = 300
      stat        = "Sum"
    }
  }
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = var.name
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          title  = "API requests and errors"
          region = var.aws_region
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiName", var.api_name, "Stage", var.api_stage],
            [".", "4XXError", ".", ".", ".", "."],
            [".", "5XXError", ".", ".", ".", "."],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          title  = "API latency (ms)"
          region = var.aws_region
          period = 60
          metrics = [
            ["AWS/ApiGateway", "Latency", "ApiName", var.api_name, "Stage", var.api_stage, { stat = "p50" }],
            ["...", { stat = "p99" }],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6
        properties = {
          title  = "Lambda invocations, errors, throttles"
          region = var.aws_region
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.lambda_function_name],
            [".", "Errors", ".", "."],
            [".", "Throttles", ".", "."],
            [".", "ConcurrentExecutions", ".", ".", { stat = "Maximum" }],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6
        properties = {
          title  = "Business: projects created vs name conflicts"
          region = var.aws_region
          stat   = "Sum"
          period = 300
          metrics = [
            [var.metrics_namespace, "ProjectsCreated", "service", var.service_name],
            [".", "ProjectNameConflicts", ".", "."],
            [".", "ColdStart", "function_name", var.lambda_function_name, "service", var.service_name],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 12, width = 24, height = 6
        properties = {
          title  = "DynamoDB consumed capacity and errors"
          region = var.aws_region
          stat   = "Sum"
          period = 60
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", var.table_name],
            [".", "ConsumedWriteCapacityUnits", ".", "."],
            [".", "ReadThrottleEvents", ".", "."],
            [".", "WriteThrottleEvents", ".", "."],
            [{
              expression = "SUM(SEARCH('{AWS/DynamoDB,TableName,Operation} MetricName=\"SystemErrors\" TableName=\"${var.table_name}\"', 'Sum', 60))"
              label      = "SystemErrors (all operations)"
              id         = "system_errors"
            }],
          ]
        }
      },
    ]
  })
}

# Cost guard rail. Notifies when forecast or actual spend crosses the monthly limit.
resource "aws_budgets_budget" "monthly" {
  count        = var.monthly_budget_usd == null ? 0 : 1
  name         = "${var.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = ["user:Project$projects-api"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_sns_topic_arns  = [aws_sns_topic.alarms.arn]
    subscriber_email_addresses = var.alarm_email == null ? [] : [var.alarm_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_sns_topic_arns  = [aws_sns_topic.alarms.arn]
    subscriber_email_addresses = var.alarm_email == null ? [] : [var.alarm_email]
  }
}

# Budgets publishes to SNS, so the topic must allow it.
data "aws_iam_policy_document" "sns" {
  statement {
    sid     = "AllowBudgets"
    actions = ["SNS:Publish"]
    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }
    resources = [aws_sns_topic.alarms.arn]
  }
  statement {
    sid     = "AllowCloudWatch"
    actions = ["SNS:Publish"]
    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }
    resources = [aws_sns_topic.alarms.arn]
  }
}

resource "aws_sns_topic_policy" "alarms" {
  arn    = aws_sns_topic.alarms.arn
  policy = data.aws_iam_policy_document.sns.json
}
