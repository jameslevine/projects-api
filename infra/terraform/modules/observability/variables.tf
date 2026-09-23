variable "name" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "lambda_function_name" {
  type = string
}

variable "api_name" {
  type = string
}

variable "api_stage" {
  type = string
}

variable "table_name" {
  type = string
}

variable "alarm_email" {
  description = "Email to subscribe to alarms and budget notifications. null to skip."
  type        = string
  default     = null
}

variable "lambda_p99_ms_threshold" {
  description = "Lambda Duration p99 (ms) above which the duration alarm fires, 3 of 3 periods."
  type        = number
  default     = 2000
}

variable "api_p99_ms_threshold" {
  description = "API Gateway Latency p99 (ms) above which the latency alarm fires, 3 of 3 periods."
  type        = number
  default     = 1500
}

variable "ddb_operations" {
  description = <<-EOT
    DynamoDB operations the application issues. AWS/DynamoDB SystemErrors is published per
    TableName + Operation only (no table-level aggregate), so the system-errors alarm sums one
    metric per operation listed here. Keep in step with repositories/*.py.
  EOT
  type        = list(string)
  default     = ["GetItem", "Query", "TransactWriteItems", "DeleteItem"]
}

variable "metrics_namespace" {
  description = "Powertools metrics namespace (POWERTOOLS_METRICS_NAMESPACE on the function)."
  type        = string
  default     = "ProjectsApi"
}

variable "service_name" {
  description = "Value of the Powertools `service` dimension (POWERTOOLS_SERVICE_NAME on the function)."
  type        = string
  default     = "projects-api"
}

variable "api_4xx_ratio_threshold" {
  description = "Fraction (0-1) of requests that may be 4XX before alarming."
  type        = number
  default     = 0.5
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD for resources tagged Project=projects-api. null to skip."
  type        = number
  default     = 20
}

variable "tags" {
  type    = map(string)
  default = {}
}
