# Production environment. Defaults are the production values; prod.tfvars restates them so the
# choices are visible in one place. alarm_email has no default on purpose: a plan fails until an
# on-call address is supplied.

variable "aws_region" {
  type    = string
  default = "eu-west-2"
}

variable "environment" {
  type    = string
  default = "prod"

  validation {
    condition     = var.environment == "prod"
    error_message = "This root is the production environment; environment must be \"prod\"."
  }
}

variable "lambda_zip_path" {
  description = "Path to build/lambda.zip produced by scripts/build_lambda.sh."
  type        = string
  default     = "../../../../build/lambda.zip"
}

variable "lambda_memory_mb" {
  type    = number
  default = 512
}

variable "lambda_reserved_concurrency" {
  description = "Reserved concurrency cap for the API function. Bounds cost and DynamoDB load; it is subtracted from the account's shared pool (default 1,000), so keep at least 100 unreserved."
  type        = number
  default     = 50

  validation {
    condition     = var.lambda_reserved_concurrency >= 1
    error_message = "Production requires a reserved concurrency cap (>= 1); -1 (unreserved) is not allowed here."
  }
}

variable "logger_sample_rate" {
  description = "POWERTOOLS_LOGGER_SAMPLE_RATE: fraction of invocations logged at DEBUG. Low in prod to bound CloudWatch cost."
  type        = string
  default     = "0.05"
}

variable "alarm_email" {
  description = <<-EOT
    Email subscribed to the alarm SNS topic and budget notifications. Required in prod: without
    it nobody is paged. Set it in prod.tfvars (or TF_VAR_alarm_email) and confirm the subscription
    email AWS sends after the first apply.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[^@]+@[^@]+$", var.alarm_email))
    error_message = "alarm_email is required in prod; nobody is paged without it."
  }
}

variable "log_retention_days" {
  description = "Retention for the Lambda, API Gateway access and WAF log groups."
  type        = number
  default     = 30
}

variable "monthly_budget_usd" {
  type    = number
  default = 100
}

variable "api_p99_ms_threshold" {
  description = "API Gateway Latency p99 (ms) above which the latency alarm fires."
  type        = number
  default     = 1500
}

variable "manage_account_cloudwatch_role" {
  description = "Create the account-level API Gateway CloudWatch Logs role. Keep true even when prod shares an account with dev (both roots then register a role and report drift); false would unset the account role."
  type        = bool
  default     = true
}

variable "enable_waf" {
  description = "Attach the WAF web ACL (managed rules + per-IP rate limit) to the stage. On in prod."
  type        = bool
  default     = true
}

variable "waf_rate_limit" {
  description = "Requests per source IP per five minutes before WAF blocks it."
  type        = number
  default     = 2000
}

variable "stage_throttle_rate" {
  description = "Stage-wide steady-state requests per second."
  type        = number
  default     = 20
}

variable "stage_throttle_burst" {
  type    = number
  default = 40
}

variable "key_throttle_rate" {
  description = "Per-API-key steady-state requests per second."
  type        = number
  default     = 5
}

variable "key_throttle_burst" {
  type    = number
  default = 10
}

variable "key_monthly_quota" {
  description = "Requests per API key per calendar month."
  type        = number
  default     = 50000
}

variable "deletion_protection" {
  description = "DynamoDB deletion protection; always on in prod."
  type        = bool
  default     = true

  validation {
    condition     = var.deletion_protection
    error_message = "deletion_protection must be true in prod."
  }
}
