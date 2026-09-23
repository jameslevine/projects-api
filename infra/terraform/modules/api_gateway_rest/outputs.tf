output "rest_api_id" {
  value = aws_api_gateway_rest_api.this.id
}

output "rest_api_name" {
  value = aws_api_gateway_rest_api.this.name
}

output "stage_name" {
  value = aws_api_gateway_stage.this.stage_name
}

output "invoke_url" {
  value = aws_api_gateway_stage.this.invoke_url
}

output "usage_plan_id" {
  value = aws_api_gateway_usage_plan.default.id
}

output "demo_api_key_id" {
  value = aws_api_gateway_api_key.demo.id
}

output "demo_api_key_value" {
  value     = aws_api_gateway_api_key.demo.value
  sensitive = true
}

output "access_log_group_name" {
  value = aws_cloudwatch_log_group.access.name
}
