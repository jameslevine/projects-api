locals {
  name = "projects-api-${var.environment}"
  tags = {
    Project     = "projects-api"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "table" {
  source              = "../../modules/dynamodb_table"
  name                = local.name
  deletion_protection = var.environment == "prod"
  tags                = local.tags
}

module "lambda" {
  source      = "../../modules/lambda_api"
  name        = local.name
  environment = var.environment
  zip_path    = var.lambda_zip_path
  table_name  = module.table.name
  table_arn   = module.table.arn
  memory_mb   = var.lambda_memory_mb
  tags        = local.tags
}

module "api" {
  source                         = "../../modules/api_gateway_rest"
  name                           = local.name
  environment                    = var.environment
  lambda_invoke_arn              = module.lambda.alias_invoke_arn
  lambda_function_name           = module.lambda.function_name
  lambda_alias_name              = module.lambda.alias_name
  manage_account_cloudwatch_role = var.manage_account_cloudwatch_role
  tags                           = local.tags
}

module "observability" {
  source               = "../../modules/observability"
  name                 = local.name
  aws_region           = var.aws_region
  lambda_function_name = module.lambda.function_name
  api_name             = module.api.rest_api_name
  api_stage            = module.api.stage_name
  table_name           = module.table.name
  alarm_email          = var.alarm_email
  monthly_budget_usd   = var.monthly_budget_usd
  api_p99_ms_threshold = var.api_p99_ms_threshold
  tags                 = local.tags
}
