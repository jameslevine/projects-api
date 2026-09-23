locals {
  tags = {
    Project     = "projects-api"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "stack" {
  source = "../../modules/stack"

  environment                    = var.environment
  aws_region                     = var.aws_region
  lambda_zip_path                = var.lambda_zip_path
  lambda_memory_mb               = var.lambda_memory_mb
  lambda_reserved_concurrency    = var.lambda_reserved_concurrency
  logger_sample_rate             = var.logger_sample_rate
  log_retention_days             = var.log_retention_days
  alarm_email                    = var.alarm_email
  monthly_budget_usd             = var.monthly_budget_usd
  api_p99_ms_threshold           = var.api_p99_ms_threshold
  enable_waf                     = var.enable_waf
  waf_rate_limit                 = var.waf_rate_limit
  stage_throttle_rate            = var.stage_throttle_rate
  stage_throttle_burst           = var.stage_throttle_burst
  key_throttle_rate              = var.key_throttle_rate
  key_throttle_burst             = var.key_throttle_burst
  key_monthly_quota              = var.key_monthly_quota
  deletion_protection            = var.deletion_protection
  manage_account_cloudwatch_role = var.manage_account_cloudwatch_role
}

# The wiring moved from this root into modules/stack (S4-404). These keep existing state
# addresses valid so a plan after the refactor shows moves, not replacements.
moved {
  from = module.table
  to   = module.stack.module.table
}

moved {
  from = module.lambda
  to   = module.stack.module.lambda
}

moved {
  from = module.api
  to   = module.stack.module.api
}

moved {
  from = module.observability
  to   = module.stack.module.observability
}

moved {
  from = module.provisioner
  to   = module.stack.module.provisioner
}

moved {
  from = module.waf
  to   = module.stack.module.waf
}
