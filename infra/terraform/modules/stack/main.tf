# One Projects API environment: table, API function, REST API, observability and (optionally)
# WAF, wired identically for every environment. Roots under envs/<env> call this module once
# and supply only the per-environment values (see variables.tf).

locals {
  name = "projects-api-${var.environment}"
  tags = merge(
    {
      Project     = "projects-api"
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags,
  )

  deletion_protection = var.deletion_protection == null ? var.environment == "prod" : var.deletion_protection
  logger_sample_rate  = var.logger_sample_rate == null ? (var.environment == "prod" ? "0.05" : "1") : var.logger_sample_rate
}

module "table" {
  source              = "../dynamodb_table"
  name                = local.name
  deletion_protection = local.deletion_protection
  tags                = local.tags
}

module "lambda" {
  source               = "../lambda_api"
  name                 = local.name
  environment          = var.environment
  zip_path             = var.lambda_zip_path
  table_name           = module.table.name
  table_arn            = module.table.arn
  memory_mb            = var.lambda_memory_mb
  reserved_concurrency = var.lambda_reserved_concurrency
  logger_sample_rate   = local.logger_sample_rate

  log_retention_days = var.log_retention_days
  tags               = local.tags
}

module "api" {
  source                         = "../api_gateway_rest"
  name                           = local.name
  environment                    = var.environment
  lambda_invoke_arn              = module.lambda.alias_invoke_arn
  lambda_function_name           = module.lambda.function_name
  lambda_alias_name              = module.lambda.alias_name
  manage_account_cloudwatch_role = var.manage_account_cloudwatch_role
  log_retention_days             = var.log_retention_days
  stage_throttle_rate            = var.stage_throttle_rate
  stage_throttle_burst           = var.stage_throttle_burst
  key_throttle_rate              = var.key_throttle_rate
  key_throttle_burst             = var.key_throttle_burst
  key_monthly_quota              = var.key_monthly_quota
  tags                           = local.tags
}

module "observability" {
  source               = "../observability"
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

module "waf" {
  count      = var.enable_waf ? 1 : 0
  source     = "../waf"
  name       = local.name
  stage_arn  = module.api.stage_arn
  rate_limit = var.waf_rate_limit

  log_retention_days = var.log_retention_days
  tags               = local.tags
}
