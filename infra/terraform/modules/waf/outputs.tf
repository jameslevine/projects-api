output "web_acl_arn" {
  description = "ARN of the web ACL associated with the stage."
  value       = aws_wafv2_web_acl.this.arn
}

output "web_acl_name" {
  value = aws_wafv2_web_acl.this.name
}

output "log_group_name" {
  description = "WAF log group, or null when logging is disabled."
  value       = one(aws_cloudwatch_log_group.waf[*].name)
}
