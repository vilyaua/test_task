provider "aws" {
  region = "us-east-1"

  assume_role {
    role_arn     = "arn:aws:iam::165820787764:role/nat-alternative-terraform"
    external_id  = "terraform-nat-build"
    session_name = "terraform"
  }
}