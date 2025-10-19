terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

data "aws_region" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  environment = var.environment
  project     = var.project
  prefix      = "${var.project}-${var.environment}"

  azs = length(var.azs) > 0 ? var.azs : slice(data.aws_availability_zones.available.names, 0, var.az_count)

  az_index_map = { for idx, az in local.azs : az => idx }

  public_subnet_cidrs = {
    for az, idx in local.az_index_map : az => cidrsubnet(var.vpc_cidr, 4, idx)
  }

  private_subnet_cidrs = {
    for az, idx in local.az_index_map : az => cidrsubnet(var.vpc_cidr, 4, idx + length(local.azs))
  }

  base_tags = merge({
    "Project"     = var.project
    "Environment" = var.environment
  }, var.tags)
}
