# S3, DynamoDB, and KMS prerequisites

```bash
aws s3api create-bucket \
  --bucket terraform-state-ravenpack \
  --region eu-central-1 \
  --create-bucket-configuration LocationConstraint=eu-central-1

aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST

# Dedicated KMS key for VPC flow logs (reused by all environments). The template lives at `infra/policies/kms-flowlogs-policy.json`; edit the ARNs if necessary before running the command below.

aws kms create-key \
  --profile default \
  --region eu-central-1 \
  --description "KMS key for RavenPack NAT flow logs" \
  --key-usage ENCRYPT_DECRYPT \
  --policy file://infra/policies/kms-flowlogs-policy.json

aws kms enable-key-rotation \
  --region eu-central-1 \
  --profile default \
  --key-id <kms-key-id-from-previous-command>

# Bucket policy allowing the deployment role to manage state objects. Update `infra/policies/terraform-state-policy.json` if your ARNs differ, then apply it:
```bash
aws s3api put-bucket-policy \
  --bucket terraform-state-ravenpack \
  --policy file://infra/policies/terraform-state-policy.json
```

Record the returned KMS key ARN and pass it to Terraform with `-var "logs_kms_key_arn=<arn>"` (or set it in the appropriate tfvars file). This single key can be shared across all environments within the account; no need to create one per environment.

# Terraform Deployment Role Setup

Use this guide to provision an IAM role that allows the Terraform user `arn:aws:iam::165820787764:user/terraform` to deploy the NAT gateway alternative infrastructure.

## 1. Create the Trust Policy
Save the trust policy that restricts `sts:AssumeRole` to the Terraform user (replace the external ID if needed) and keep the IAM user limited to that role. The JSON templates live under `infra/policies/` and can be adjusted before you run the commands below.

```bash
aws iam put-user-policy \
  --user-name terraform \
  --policy-name TerraformAssumeRoleOnly \
  --policy-document file://infra/policies/terraform-user-policy.json
```

Create the role and cap the session duration to three hours.

```bash
aws iam create-role \
  --role-name nat-alternative-terraform \
  --assume-role-policy-document file://infra/policies/terraform-role-trust.json \
  --description "Terraform role for NAT alternative deployment" \
  --max-session-duration 10800

# Update trust policy if the role already exists
aws iam update-assume-role-policy \
  --role-name nat-alternative-terraform \
  --policy-document file://infra/policies/terraform-role-trust.json
```

## 2. Attach Deployment Permissions
Start with a broad policy that covers VPC networking, load balancers, Lambda, observability, and IAM pass-role requirements. Tighten resources once the Terraform modules are finalized.

```bash
aws iam put-role-policy \
  --role-name nat-alternative-terraform \
  --policy-name TerraformNATPolicy \
  --policy-document file://infra/policies/nat-alternative-terraform-policy.json

# The DynamoDB resource scope in `nat-alternative-terraform-policy.json` uses a
# wildcard region so Terraform can acquire locks even if the backend config or
# runner environment shifts regions. Update the account ID or table name if your
# setup diverges from the defaults above.
#
# `iam:TagRole` is included so Terraform can apply the tags defined in
# `aws_iam_role.flow_logs`. Reapply the inline policy whenever you tighten role
# permissions to keep this capability.

# Adjust the S3 key prefixes above (envs/*/terraform.tfstate) if your backend uses a different path.
```

## 3. Configure Terraform to Assume the Role
Update the AWS provider configuration so Terraform sessions use the new role and external ID.

```hcl
provider "aws" {
  region = "us-east-1"

  assume_role {
    role_arn     = "arn:aws:iam::165820787764:role/nat-alternative-terraform"
    external_id  = "terraform-nat-build"
    session_name = "terraform"
  }
}
```

## 4. Validate the Role
Test the trust relationship by assuming the role with base credentials and ensure temporary keys are returned.

```bash
aws sts assume-role --profile terraform \
  --role-arn arn:aws:iam::165820787764:role/nat-alternative-terraform \
  --role-session-name manual-test \
  --external-id terraform-nat-build
```

Review CloudTrail for failed actions and tighten the permissions policy as soon as module-specific ARNs are known.

## 5. Update KMS Policy for Flow Logs
When the KMS key policy changes (e.g., to include new log-group patterns), refresh it so CloudWatch Logs can continue encrypting flow logs.

```bash
aws kms put-key-policy \
  --region eu-central-1 \
  --profile default \
  --key-id <kms-key-id-or-alias> \
  --policy-name default \
  --policy file://infra/policies/kms-flowlogs-policy.json
```

Ensure `infra/policies/kms-flowlogs-policy.json` matches the pattern Terraform uses (see `data.aws_iam_policy_document.logs_kms` for the expected ARN).
> Shortcut: run `./infra/scripts/bootstrap.sh --profile terraform-role --skip-iam` to reuse the Terraform init/plan flow once IAM policies are in place.
