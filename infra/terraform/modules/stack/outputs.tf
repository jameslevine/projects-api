# Re-exported so every envs/<env> root exposes the same output names (README, runbook and the
# scripts read api_url, demo_api_key_value, usage_plan_id, lambda_function_name).

output "api_url" {
  description = "Base URL of the deployed stage."
  value       = module.api.invoke_url
}

output "rest_api_id" {
  value = module.api.rest_api_id
}

output "stage_arn" {
  value = module.api.stage_arn
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

output "access_log_group_name" {
  value = module.api.access_log_group_name
}

output "table_name" {
  value = module.table.name
}

output "table_arn" {
  value = module.table.arn
}

output "lambda_function_name" {
  value = module.lambda.function_name
}

output "lambda_log_group_name" {
  value = module.lambda.log_group_name
}

output "dashboard_name" {
  value = module.observability.dashboard_name
}

output "alarm_topic_arn" {
  value = module.observability.alarm_topic_arn
}

output "waf_web_acl_arn" {
  description = "Web ACL attached to the stage, or null when enable_waf is false."
  value       = one(module.waf[*].web_acl_arn)
}
