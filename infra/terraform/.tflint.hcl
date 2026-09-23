# tflint configuration for every directory under infra/terraform.
# Run from infra/terraform:  tflint --init && tflint --recursive --config "$(pwd)/.tflint.hcl"
# (Makefile target tf-lint; CI job terraform-scan.)

config {
  format = "compact"
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "aws" {
  enabled = true
  version = "0.38.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
