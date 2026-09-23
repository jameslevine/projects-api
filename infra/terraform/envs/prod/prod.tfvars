# Production values. Every line restates the default in variables.tf so the choices are visible
# here; change them in both places or drop the line to fall back to the default.
aws_region                  = "eu-west-2"
environment                 = "prod"
lambda_memory_mb            = 512
lambda_reserved_concurrency = 50
logger_sample_rate          = "0.05"
log_retention_days          = 30
monthly_budget_usd          = 100
enable_waf                  = true
waf_rate_limit              = 2000
stage_throttle_rate         = 20
stage_throttle_burst        = 40
key_throttle_rate           = 5
key_throttle_burst          = 10
key_monthly_quota           = 50000
deletion_protection         = true

# REQUIRED, no default: the on-call address subscribed to alarms and budget notifications.
# `make tf-plan ENV=prod` fails with "No value for required variable" until it is set here or
# as TF_VAR_alarm_email. Confirm the subscription email AWS sends after the first apply.
# alarm_email = "oncall@example.com"
