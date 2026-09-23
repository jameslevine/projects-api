variable "name" {
  type = string
}

variable "environment" {
  type = string
}

variable "stage_name" {
  type    = string
  default = "live"
}

variable "lambda_invoke_arn" {
  type = string
}

variable "lambda_function_name" {
  type = string
}

variable "lambda_alias_name" {
  type = string
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "stage_throttle_rate" {
  description = "Stage-wide steady-state requests per second."
  type        = number
  default     = 50
}

variable "stage_throttle_burst" {
  type    = number
  default = 100
}

variable "key_throttle_rate" {
  description = "Per-key requests per second."
  type        = number
  default     = 10
}

variable "key_throttle_burst" {
  type    = number
  default = 20
}

variable "key_monthly_quota" {
  type    = number
  default = 10000
}

variable "manage_account_cloudwatch_role" {
  description = "Create the account-level API Gateway CloudWatch role. Set false if the account already has one."
  type        = bool
  default     = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
