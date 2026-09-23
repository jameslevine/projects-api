output "api_url" {
  description = "Base URL of the deployed stage."
  value       = module.api.invoke_url
}

output "demo_api_key_id" {
  value = module.api.demo_api_key_id
}

output "demo_api_key_value" {
  description = "Read with: terraform output -raw demo_api_key_value"
  value       = module.api.demo_api_key_value
  sensitive   = true
}

output "usage_plan_id" {
  value = module.api.usage_plan_id
}

output "table_name" {
  value = module.table.name
}

output "lambda_function_name" {
  value = module.lambda.function_name
}

output "provisioner_function_name" {
  value = module.provisioner.function_name
}

output "provisioner_dlq_url" {
  description = "DLQ for provisioner batches that exhausted their retries."
  value       = module.provisioner.dlq_url
}

output "dashboard_name" {
  value = module.observability.dashboard_name
}

output "waf_web_acl_arn" {
  description = "Web ACL attached to the stage, or null when enable_waf is false."
  value       = one(module.waf[*].web_acl_arn)
}
