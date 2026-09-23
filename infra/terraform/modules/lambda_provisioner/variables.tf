variable "name" {
  description = "Function name, also the prefix for the role, DLQ, log group and alarms (for example projects-api-dev-provisioner)."
  type        = string
}

variable "environment" {
  description = "Environment name passed to the function as ENV (dev or prod)."
  type        = string
}

variable "zip_path" {
  description = "Path to the built deployment package (scripts/build_lambda.sh); shared with the API function."
  type        = string
}

variable "table_name" {
  description = "Projects table name (TABLE_NAME for the function)."
  type        = string
}

variable "table_arn" {
  description = "Projects table ARN; the function may only UpdateItem on it."
  type        = string
}

variable "stream_arn" {
  description = "ARN of the table's DynamoDB stream the event source mapping consumes."
  type        = string
}

variable "alarm_topic_arn" {
  description = "SNS topic that receives the DLQ-depth and function-error alarms (both ALARM and OK)."
  type        = string
}

variable "memory_mb" {
  description = "Function memory in MB."
  type        = number
  default     = 512
}

variable "timeout_seconds" {
  description = "Function timeout; provisioning a batch of up to 10 projects must fit inside it."
  type        = number
  default     = 60
}

variable "reserved_concurrency" {
  description = "-1 for unreserved. A cap bounds how many batches are provisioned concurrently."
  type        = number
  default     = -1
}

variable "log_level" {
  description = "LOG_LEVEL for the function."
  type        = string
  default     = "INFO"
}

variable "log_retention_days" {
  description = "Retention for the function's log group."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags applied to every resource in the module."
  type        = map(string)
  default     = {}
}
