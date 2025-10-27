environment       = "test"
project           = "nat-alternative"
az_count          = 2
vpc_cidr          = "10.0.0.0/16"
allowed_ssh_cidrs = []
logs_kms_key_arn = "arn:aws:kms:eu-central-1:165820787764:key/f386504d-ca09-4e54-b8bf-29842e106515"
tags = {
  "Owner" = "terraform"
}
