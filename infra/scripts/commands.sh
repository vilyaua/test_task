AWS_PROFILE=terraform-role terraform init -migrate-state -backend-config=backend-test.hcl
AWS_PROFILE=terraform-role terraform plan -var-file=environments/test/vars.tfvars

AWS_PROFILE=terraform-role ./scripts/verify_nat.sh test
