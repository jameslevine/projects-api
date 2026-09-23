output "api_url" {
  description = "Base URL of the deployed stage."
  value       = module.stack.api_url
}

output "demo_api_key_id" {
  value = module.stack.demo_api_key_id
}

output "demo_api_key_value" {
  description = "Read with: terraform output -raw demo_api_key_value"
  value       = module.stack.demo_api_key_value
  sensitive   = true
}

output "usage_plan_id" {
  value = module.stack.usage_plan_id
}

output "table_name" {
  value = module.stack.table_name
}

output "lambda_function_name" {
  value = module.stack.lambda_function_name
}

output "provisioner_function_name" {
  value = module.stack.provisioner_function_name
}

output "provisioner_dlq_url" {
  description = "DLQ for provisioner batches that exhausted their retries."
  value       = module.stack.provisioner_dlq_url
}

output "dashboard_name" {
  value = module.stack.dashboard_name
}

output "waf_web_acl_arn" {
  description = "Web ACL attached to the stage (enable_waf defaults to true in prod)."
  value       = module.stack.waf_web_acl_arn
}
