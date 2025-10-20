# Local Development Checklist

Use this checklist to validate changes before opening a pull request or pushing to `main`.

## 1. Backend & Credentials
- Install Terraform ≥ 1.6, TFLint ≥ 0.50, and tfsec.
- Configure AWS profiles so you can assume the deployment role easily (see below).
- Example `~/.aws/credentials` entries:
  ```ini
  [terraform]
  aws_access_key_id = <terraform-user-access-key>
  aws_secret_access_key = <terraform-user-secret>

  [admin]
  aws_access_key_id = <admin-access-key>
  aws_secret_access_key = <admin-secret>
  ```
- Initialise/migrate the remote backend once per environment:
  ```bash
  cd infra
  terraform init -migrate-state \
    -backend-config=backend-test.hcl   # or backend-prod.hcl
  ```

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

## 4. Assume the Terraform role locally
- For day-to-day work, create an AWS CLI profile that assumes `nat-alternative-terraform` from either your admin user or the `terraform` IAM user. Add the following to `~/.aws/config`:
  ```ini
  [profile terraform-role]
  role_arn = arn:aws:iam::165820787764:role/nat-alternative-terraform
  source_profile = terraform              # IAM user "terraform"
  external_id = terraform-nat-build
  region = eu-central-1
  ```
- Run Terraform with `AWS_PROFILE=terraform-role` so the backend has S3/DynamoDB access. The provider no longer re-assumes the role, so the profile (or workflow) must supply the final credentials.

## 4. Probe Script (optional)
After running `terraform apply`, verify NAT connectivity:
```bash
./scripts/verify_nat.sh test
```

## 5. Backend Notes
- Environment variables live in `infra/environments/<env>/vars.tfvars` (`prod`, `test`, etc.).
- Backend configs live in `infra/backend-*.hcl` (e.g., `backend-test.hcl`, `backend-prod.hcl`). Pair each var-file with the matching backend when running `terraform init`.

## 6. GitHub Actions Parity
These commands mirror the CI pipeline, so green results locally usually indicate the workflows will pass. If the repository uses additional tools (e.g., tfsec), install and run them as needed (`tfsec infra`).
