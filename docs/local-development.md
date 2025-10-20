# Local Development Checklist

Use this checklist to validate changes before opening a pull request or pushing to `main`.

## 1. Environment Setup
- Install Terraform ≥ 1.6 and TFLint ≥ 0.50.
- Authenticate with AWS using the `terraform` profile or via OIDC tokens (see `docs/terraform-role-setup.md`).
- Export `AWS_PROFILE=terraform` or configure `infra/providers.tf` variables accordingly.
- Ensure remote state is initialised:
  ```bash
  cd infra
  terraform init -migrate-state
  ```
  (Migrates local `terraform.tfstate` into the S3 backend defined in `backend.tf`.)

## 2. Formatting & Linting
Run from the repository root:

```bash
# Format Terraform
cd infra
terraform fmt -recursive

# Check formatting
terraform fmt -check -recursive

# Initialize TFLint (first run)
tflint --init

# Run TFLint
tflint

# tfsec (security scanning)
tfsec
```

Fix warnings such as unused locals or data sources before committing.

## 3. Terraform Validate & Plan
```bash
terraform validate
terraform plan -var-file=environments/test/vars.tfvars
```
Review the plan output and ensure only intended changes are present.

## 4. Probe Script (optional)
After running `terraform apply`, verify NAT connectivity:
```bash
./scripts/verify_nat.sh test
```

## 5. GitHub Actions Parity
These commands mirror the CI pipeline, so green results locally usually indicate the workflows will pass. If the repository uses additional tools (e.g., tfsec), install and run them as needed (`tfsec infra`).
