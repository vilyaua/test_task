provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile == "" ? null : var.aws_profile

  assume_role {
    role_arn     = "arn:aws:iam::165820787764:role/nat-alternative-terraform"
    external_id  = "terraform-nat-build"
    session_name = "terraform"
  }
}
