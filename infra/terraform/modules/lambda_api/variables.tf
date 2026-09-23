variable "name" {
  type = string
}

variable "environment" {
  type = string
}

variable "zip_path" {
  description = "Path to the built deployment package (scripts/build_lambda.sh)."
  type        = string
}

variable "table_name" {
  type = string
}

variable "table_arn" {
  type = string
}

variable "memory_mb" {
  type    = number
  default = 512
}

variable "timeout_seconds" {
  type    = number
  default = 10
}

variable "reserved_concurrency" {
  description = "-1 for unreserved. A cap protects downstream and bounds cost."
  type        = number
  default     = -1
}

variable "log_level" {
  type    = string
  default = "INFO"
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "tags" {
  type    = map(string)
  default = {}
}
