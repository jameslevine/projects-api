terraform {
  required_version = ">= 1.3"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Partial backend config. Supply the bucket/table via:
  #   terraform init -backend-config=backend.hcl
  # (see backend.example.hcl; created by infra/terraform/bootstrap)
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = local.tags
  }
}
