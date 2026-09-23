variable "aws_region" {
  type    = string
  default = "eu-west-2"
}

variable "environment" {
  type    = string
  default = "dev"
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

variable "alarm_email" {
  description = <<-EOT
    Email subscribed to the alarm SNS topic and budget notifications. WITHOUT THIS NOBODY IS
    PAGED: alarms only change state in the console. Set it in <env>.tfvars for any environment
    somebody relies on and confirm the subscription email AWS sends. null skips the subscription.
  EOT
  type        = string
  default     = null
}

variable "log_retention_days" {
  description = "Retention for the Lambda, API Gateway access and WAF log groups. Raise for prod."
  type        = number
  default     = 14
}

variable "monthly_budget_usd" {
  type    = number
  default = 20
}

variable "api_p99_ms_threshold" {
  description = "API Gateway Latency p99 (ms) above which the latency alarm fires."
  type        = number
  default     = 1500
}

variable "manage_account_cloudwatch_role" {
  type    = bool
  default = true
}

variable "enable_waf" {
  description = "Attach a WAF web ACL (managed rules + per-IP rate limit) to the stage. Off by default: about USD 5 per ACL, USD 1 per rule and USD 0.60 per million requests each month."
  type        = bool
  default     = false
}

variable "waf_rate_limit" {
  description = "Requests per source IP per five minutes before WAF blocks it (when enable_waf)."
  type        = number
  default     = 2000
}
