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
  type    = string
  default = null
}

variable "monthly_budget_usd" {
  type    = number
  default = 20
}

variable "manage_account_cloudwatch_role" {
  type    = bool
  default = true
}
