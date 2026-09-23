variable "name" {
  type = string
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "stream_enabled" {
  description = "Enable DynamoDB Streams (needed by the Slice 4 provisioning pipeline)."
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
