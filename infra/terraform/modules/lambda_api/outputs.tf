output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "function_arn" {
  value = aws_lambda_function.this.arn
}

output "alias_arn" {
  value = aws_lambda_alias.live.arn
}

output "alias_invoke_arn" {
  value = aws_lambda_alias.live.invoke_arn
}

output "alias_name" {
  value = aws_lambda_alias.live.name
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.this.name
}

output "role_name" {
  value = aws_iam_role.this.name
}
