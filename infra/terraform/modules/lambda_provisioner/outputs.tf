output "function_name" {
  value = aws_lambda_function.this.function_name
}

output "function_arn" {
  value = aws_lambda_function.this.arn
}

output "dlq_arn" {
  value = aws_sqs_queue.dlq.arn
}

output "dlq_url" {
  description = "Queue URL, for inspecting or redriving failed batches."
  value       = aws_sqs_queue.dlq.url
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.this.name
}

output "event_source_mapping_uuid" {
  value = aws_lambda_event_source_mapping.stream.uuid
}
