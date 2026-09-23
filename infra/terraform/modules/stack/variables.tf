# Everything that differs between environments is a variable here; the wiring in main.tf is
# identical for every environment. Defaults are the dev values so that envs/dev can pass only
# what it overrides and envs/prod states every stricter value explicitly.

variable "environment" {
  description = "Environment name; suffixes every resource name (projects-api-<environment>) and is the ENV seen by the application."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.environment))
    error_message = "environment must be 2-16 characters of lower-case letters, digits and hyphens, starting with a letter."
  }
}

variable "aws_region" {
  description = "Region the stack is deployed to; used for dashboard widgets."
  type        = string
}

variable "lambda_zip_path" {
  description = "Path to build/lambda.zip produced by scripts/build_lambda.sh, relative to the calling root module."
  type        = string
}

variable "lambda_memory_mb" {
  description = "Memory (and proportional CPU) for the API function."
  type        = number
  default     = 512
}

variable "lambda_reserved_concurrency" {
  description = "Reserved concurrency for the API function; -1 leaves it unreserved. A cap bounds cost and protects DynamoDB; it is subtracted from the account's shared pool."
  type        = number
  default     = -1

  validation {
    condition     = var.lambda_reserved_concurrency == -1 || var.lambda_reserved_concurrency >= 1
    error_message = "lambda_reserved_concurrency must be -1 (unreserved) or a positive number."
  }
}

variable "logger_sample_rate" {
  description = "POWERTOOLS_LOGGER_SAMPLE_RATE: fraction of invocations logged at DEBUG. null picks 0.05 for prod and 1 otherwise."
  type        = string
  default     = null

  validation {
    condition     = var.logger_sample_rate == null || can(tonumber(var.logger_sample_rate)) && try(tonumber(var.logger_sample_rate) >= 0 && tonumber(var.logger_sample_rate) <= 1, false)
    error_message = "logger_sample_rate must be null or a number between 0 and 1 as a string, for example \"0.05\"."
  }
}

variable "log_retention_days" {
  description = "Retention for the Lambda, API Gateway access and WAF log groups."
  type        = number
  default     = 14
}

variable "alarm_email" {
  description = <<-EOT
    Email subscribed to the alarm SNS topic and budget notifications. WITHOUT THIS NOBODY IS
    PAGED: alarms only change state in the console. null skips the subscription (the prod root
    refuses null).
  EOT
  type        = string
  default     = null
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD for resources tagged Project=projects-api; null skips the budget."
  type        = number
  default     = 20
}

variable "api_p99_ms_threshold" {
  description = "API Gateway Latency p99 (ms) above which the latency alarm fires."
  type        = number
  default     = 1500
}

variable "enable_waf" {
  description = "Attach a WAF web ACL (managed rules + per-IP rate limit) to the stage. About USD 5 per ACL, USD 1 per rule and USD 0.60 per million requests each month."
  type        = bool
  default     = false
}

variable "waf_rate_limit" {
  description = "Requests per source IP per five minutes before WAF blocks it (when enable_waf)."
  type        = number
  default     = 2000
}

variable "stage_throttle_rate" {
  description = "Stage-wide steady-state requests per second."
  type        = number
  default     = 50
}

variable "stage_throttle_burst" {
  description = "Stage-wide burst limit."
  type        = number
  default     = 100
}

variable "key_throttle_rate" {
  description = "Per-API-key steady-state requests per second (usage plan)."
  type        = number
  default     = 10
}

variable "key_throttle_burst" {
  description = "Per-API-key burst limit (usage plan)."
  type        = number
  default     = 20
}

variable "key_monthly_quota" {
  description = "Requests per API key per calendar month (usage plan quota)."
  type        = number
  default     = 10000
}

variable "deletion_protection" {
  description = "DynamoDB deletion protection. null enables it for prod and disables it otherwise."
  type        = bool
  default     = null
}

variable "manage_account_cloudwatch_role" {
  description = <<-EOT
    Create the account-level API Gateway CloudWatch Logs role and register it with
    aws_api_gateway_account. That setting is one per AWS account and region: if two environments
    share an account and region both roots register their own role and Terraform reports drift
    on every plan, but logging works. Setting false in the api_gateway_rest module unsets the
    account role, so keep it true unless the account already has a role managed elsewhere.
  EOT
  type        = bool
  default     = true
}

variable "tags" {
  description = "Extra tags merged over Project/Environment/ManagedBy on every resource."
  type        = map(string)
  default     = {}
}
