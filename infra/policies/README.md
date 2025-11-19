# IAM Policies and Roles for CDK Deployment

This directory contains IAM policies and trust relationships needed for deploying the NAT Gateway Alternative infrastructure using AWS CDK.

## Required Policies

### 1. `github-actions-policy.json`
**Purpose:** Permissions for GitHub Actions workflow to deploy/destroy infrastructure via CDK.

**Used by:** `github-actions-cdk` IAM role (or similar)

**Key Permissions:**
- CloudFormation operations (create/update/delete stacks)
- EC2, Lambda, Auto Scaling, EventBridge, CloudWatch, Logs
- IAM role and instance profile management
- S3 (for CDK assets/bootstrap)
- SSM for probe instance management

**Note:** This policy replaces the Terraform-specific policy and includes CloudFormation permissions instead of S3/DynamoDB state management.

### 2. `cdk-deployment-policy.json`
**Purpose:** Comprehensive deployment policy for CDK operations (alternative to github-actions-policy.json).

**Used by:** CDK deployment roles

**Key Permissions:**
- Full CloudFormation stack lifecycle management
- All AWS service permissions needed for the infrastructure
- IAM role management for Lambda, EC2 instances
- S3 access for CDK bootstrap and assets

### 3. `github-actions-trust.json`
**Purpose:** Trust relationship for GitHub Actions OIDC authentication.

**Used by:** IAM role that GitHub Actions assumes

**Key Features:**
- Allows `sts:AssumeRoleWithWebIdentity` from GitHub OIDC provider
- Scoped to specific repository (`vilyaua/test_task`)
- Supports branches, tags, environments, and pull requests

### 4. `cdk-deployment-role-trust.json`
**Purpose:** Alternative trust relationship for CDK deployment roles (same as github-actions-trust.json but with generic naming).

**Used by:** CDK deployment IAM roles

### 5. `kms-flowlogs-policy.json`
**Purpose:** KMS key policy for encrypting VPC Flow Logs and CloudWatch Logs.

**Used by:** KMS key for log encryption

**Key Features:**
- Root account access
- CloudWatch Logs service permissions
- Scoped to specific log group patterns

## Setup Instructions

### 1. Create GitHub Actions IAM Role

```bash
# Create the role with OIDC trust
aws iam create-role \
  --role-name github-actions-cdk \
  --assume-role-policy-document file://github-actions-trust.json \
  --description "GitHub Actions OIDC role for CDK deployments"

# Attach the deployment policy
aws iam put-role-policy \
  --role-name github-actions-cdk \
  --policy-name GitHubActionsCDKDeployment \
  --policy-document file://github-actions-policy.json
```

### 2. Create OIDC Provider (if not exists)

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list cf23df2207d99a74fbe169e3eba035e633b65d94
```

### 3. Configure GitHub Variables

Set these in your GitHub repository settings:

```bash
gh variable set AWS_ROLE_TO_ASSUME --body "arn:aws:iam::197496953931:role/github-actions-cdk"
gh variable set AWS_REGION --body "eu-central-1"
gh secret set AWS_ACCOUNT_ID --body "197496953931"
```

### 4. Bootstrap CDK (one-time per account/region)

```bash
cdk bootstrap aws://197496953931/eu-central-1
```

## Differences from Terraform Setup

### Removed (Terraform-specific):
- ❌ S3 state bucket permissions (`terraform-state-policy.json`)
- ❌ DynamoDB lock table permissions
- ❌ Terraform user/role trust policies
- ❌ External ID conditions (not needed for OIDC)

### Added (CDK-specific):
- ✅ CloudFormation stack management permissions
- ✅ S3 permissions for CDK bootstrap and assets (not state)
- ✅ OIDC-based authentication (no static credentials)

## Policy Updates

When updating policies:
1. Test changes in a development environment first
2. Update the policy document
3. Apply with `aws iam put-role-policy`
4. Verify GitHub Actions workflow can still deploy

## Security Notes

- Policies use `Resource: "*"` for many actions due to service limitations (e.g., `ec2:DescribeInstances` doesn't support resource-level permissions)
- IAM permissions are scoped to necessary operations only
- OIDC trust is limited to specific repository and branches
- KMS key policy restricts log encryption to specific log group patterns
