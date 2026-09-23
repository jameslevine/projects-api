variable "name" {
  description = "Base name for the web ACL, its rules' metrics and the log group (for example projects-api-dev)."
  type        = string
}

variable "stage_arn" {
  description = "ARN of the API Gateway REST stage to associate the web ACL with."
  type        = string
}

variable "rate_limit" {
  description = "Maximum requests from one source IP in any five-minute window before it is blocked."
  type        = number
  default     = 2000

  validation {
    condition     = var.rate_limit >= 100 && var.rate_limit <= 2000000000
    error_message = "rate_limit must be between 100 and 2,000,000,000 (WAF rate-based rule bounds)."
  }
}

variable "enable_logging" {
  description = "Send WAF logs (with x-api-key redacted) to a CloudWatch log group."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "Retention for the WAF log group."
  type        = number
  default     = 14
}

variable "tags" {
  type    = map(string)
  default = {}
}
