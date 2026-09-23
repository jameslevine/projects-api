# Optional edge protection for the REST API stage: AWS managed rule groups plus a per-IP
# rate limit. REGIONAL scope because API Gateway REST stages are regional resources.
#
# Cost: roughly USD 5 per web ACL per month, USD 1 per rule per month and USD 0.60 per million
# requests, so it is behind a default-off flag in the environment (see envs/dev enable_waf).

resource "aws_wafv2_web_acl" "this" {
  name        = "${var.name}-web-acl"
  description = "Managed rules and per-IP rate limiting for ${var.name}"
  scope       = "REGIONAL"
  tags        = var.tags

  default_action {
    allow {}
  }

  # 1. Core protections: SQLi, XSS, path traversal, bad user agents, oversized bodies.
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-common-rule-set"
      sampled_requests_enabled   = true
    }
  }

  # 2. Known exploit patterns (including Log4j JNDI lookups) in request bodies and headers.
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  # 3. Per-source-IP rate limit, evaluated over a rolling five-minute window. Complements the
  #    usage-plan throttles, which only apply after a valid key has been presented.
  rule {
    name     = "RateLimitPerIp"
    priority = 3

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = var.rate_limit
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-rate-limit-per-ip"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.name}-web-acl"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "stage" {
  resource_arn = var.stage_arn
  web_acl_arn  = aws_wafv2_web_acl.this.arn
}

# WAF only accepts CloudWatch log groups whose name starts with "aws-waf-logs-".
resource "aws_cloudwatch_log_group" "waf" {
  count             = var.enable_logging ? 1 : 0
  name              = "aws-waf-logs-${var.name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_wafv2_web_acl_logging_configuration" "this" {
  count                   = var.enable_logging ? 1 : 0
  resource_arn            = aws_wafv2_web_acl.this.arn
  log_destination_configs = [aws_cloudwatch_log_group.waf[0].arn]

  # Never write API keys to logs, even sampled ones.
  redacted_fields {
    single_header {
      name = "x-api-key"
    }
  }
}
