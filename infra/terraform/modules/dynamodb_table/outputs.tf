output "name" {
  value = aws_dynamodb_table.this.name
}

output "arn" {
  value = aws_dynamodb_table.this.arn
}

output "stream_arn" {
  value = aws_dynamodb_table.this.stream_arn
}
