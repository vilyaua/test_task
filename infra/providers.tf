provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile == "" ? null : var.aws_profile
}
