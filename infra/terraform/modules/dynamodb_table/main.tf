# Single-table design. Generic PK/SK so many entity types share one table.
# Partition key for project records is PROJECT#<projectId>.

resource "aws_dynamodb_table" "this" {
  name                        = var.name
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "PK"
  range_key                   = "SK"
  deletion_protection_enabled = var.deletion_protection
  table_class                 = "STANDARD"

  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }
  attribute {
    name = "GSI1PK"
    type = "S"
  }
  attribute {
    name = "GSI1SK"
    type = "S"
  }

  # Owner -> projects, in creation order.
  global_secondary_index {
    name            = "GSI1"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true # AWS-owned key. Set kms_key_arn for a customer-managed key.
  }

  stream_enabled   = var.stream_enabled
  stream_view_type = var.stream_enabled ? "NEW_AND_OLD_IMAGES" : null

  tags = var.tags
}
