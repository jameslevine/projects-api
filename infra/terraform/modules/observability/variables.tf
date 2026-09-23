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
  type    = number
  default = 2000
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
