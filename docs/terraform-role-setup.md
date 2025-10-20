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

# Dedicated KMS key for VPC flow logs (reused by all environments)
cat > kms-flowlogs-policy.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EnableRootAccountAccess",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::165820787764:root" },
      "Action": "kms:*",
      "Resource": "*"
    },
    {
      "Sid": "AllowCloudWatchLogsEncryption",
      "Effect": "Allow",
      "Principal": { "Service": "logs.eu-central-1.amazonaws.com" },
      "Action": [
        "kms:Encrypt*",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "kms:EncryptionContext:aws:logs:arn": "arn:aws:logs:eu-central-1:165820787764:log-group:/aws/vpc/nat-alternative-*"
        }
      }
    }
  ]
}
JSON

aws kms create-key \
  --profile default \
  --region eu-central-1 \
  --description "KMS key for RavenPack NAT flow logs" \
  --key-usage ENCRYPT_DECRYPT \
  --policy file://kms-flowlogs-policy.json

aws kms enable-key-rotation \
  --region eu-central-1 \
  --profile default \
  --key-id <kms-key-id-from-previous-command>
```

Record the returned KMS key ARN and pass it to Terraform with `-var "logs_kms_key_arn=<arn>"` (or set it in the appropriate tfvars file). This single key can be shared across all environments within the account; no need to create one per environment.

# Terraform Deployment Role Setup

Use this guide to provision an IAM role that allows the Terraform user `arn:aws:iam::165820787764:user/terraform` to deploy the NAT gateway alternative infrastructure.

## 1. Create the Trust Policy
Save the trust policy that restricts `sts:AssumeRole` to the Terraform user (replace the external ID if needed).

```bash
cat > trust-policy.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::165820787764:user/terraform" },
      "Action": "sts:AssumeRole",
      "Condition": { "StringEquals": { "sts:ExternalId": "terraform-nat-build" } }
    },
    {
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::165820787764:role/github-actions-terraform" },
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON
```

Create the role and cap the session duration to three hours.

```bash
aws iam create-role \
  --role-name nat-alternative-terraform \
  --assume-role-policy-document file://trust-policy.json \
  --description "Terraform role for NAT alternative deployment" \
  --max-session-duration 10800

# Update trust policy if the role already exists
aws iam update-assume-role-policy \
  --role-name nat-alternative-terraform \
  --policy-document file://trust-policy.json
```

## 2. Attach Deployment Permissions
Start with a broad policy that covers VPC networking, load balancers, Lambda, observability, and IAM pass-role requirements. Tighten resources once the Terraform modules are finalized.

```bash
cat > permissions-policy.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "elasticloadbalancing:*",
        "autoscaling:*",
        "lambda:*",
        "logs:*",
        "cloudwatch:*",
        "iam:CreateServiceLinkedRole",
        "iam:GetRole",
        "iam:PassRole",
        "ssm:*",
        "s3:*"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:CreateServiceLinkedRole",
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "iam:AWSServiceName": [
            "elasticloadbalancing.amazonaws.com",
            "autoscaling.amazonaws.com"
          ]
        }
      }
    }
  ]
}
JSON
```

Attach the inline policy to the role:

```bash
aws iam put-role-policy \
  --role-name nat-alternative-terraform \
  --policy-name TerraformNATPolicy \
  --policy-document file://permissions-policy.json
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
