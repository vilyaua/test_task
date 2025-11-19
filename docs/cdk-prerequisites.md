# CDK Prerequisites and Setup

This document outlines the prerequisites and setup steps needed for deploying the NAT Gateway Alternative infrastructure using AWS CDK.

## Comparison: Terraform vs CDK Prerequisites

### Terraform Prerequisites (Legacy)
1. **S3 Bucket** - For Terraform state storage
   - Manual creation: `terraform-state-ravenpack`
   - Bucket policy for role access
   - Versioning enabled

2. **DynamoDB Table** - For state locking
   - Manual creation: `terraform-locks`
   - Prevents concurrent modifications

3. **IAM User** - `terraform` user with access keys
   - Static credentials stored in GitHub secrets or local config
   - Limited permissions to assume deployment role

4. **IAM Role** - `nat-alternative-terraform` deployment role
   - Trust relationship with IAM user (external ID)
   - Trust relationship with GitHub Actions role
   - Permissions for all AWS resources

5. **GitHub Actions IAM Role** - `github-actions-terraform`
   - OIDC trust relationship
   - Permissions to assume deployment role
   - Permissions for S3 state bucket and DynamoDB locks

### CDK Prerequisites (Current)

1. **CDK Bootstrap** ⭐ **One-time setup per account/region**
   - Automatically creates:
     - S3 bucket for CDK assets (templates, Lambda code)
     - IAM roles for CloudFormation operations
     - ECR repositories (if using Docker assets)
   - Command: `cdk bootstrap aws://ACCOUNT-ID/REGION`

2. **GitHub Actions IAM Role** - `github-actions-cdk`
   - OIDC trust relationship (same as Terraform)
   - Permissions for CloudFormation stack operations
   - Permissions for all AWS resources (EC2, Lambda, IAM, etc.)
   - **No separate deployment role needed** - GitHub Actions role has direct permissions

3. **KMS Key** (Optional but recommended)
   - For encrypting CloudWatch Logs and VPC Flow Logs
   - Can use existing key or CDK will create one

## Setup Steps

### 1. Bootstrap CDK (One-Time Per Account/Region)

```bash
# Bootstrap CDK in your AWS account
cdk bootstrap aws://197496953931/eu-central-1
```

**What this creates:**
- S3 bucket: `cdk-<account-id>-<region>-assets` (for CDK assets)
- IAM roles: `cdk-<qualifier>-*` (for CloudFormation operations)
- ECR repositories: (if using Docker assets)

**Note:** Bootstrap is idempotent - safe to run multiple times.

### 2. Create GitHub Actions IAM Role

```bash
# Create OIDC provider (if not exists)
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list cf23df2207d99a74fbe169e3eba035e633b65d94

# Create IAM role with OIDC trust
aws iam create-role \
  --role-name github-actions-cdk \
  --assume-role-policy-document file://infra/policies/github-actions-trust.json \
  --description "GitHub Actions OIDC role for CDK deployments"

# Attach deployment policy
aws iam put-role-policy \
  --role-name github-actions-cdk \
  --policy-name GitHubActionsCDKDeployment \
  --policy-document file://infra/policies/github-actions-policy.json
```

### 3. Configure GitHub Variables

```bash
# Set GitHub repository variables
gh variable set AWS_ROLE_TO_ASSUME --body "arn:aws:iam::197496953931:role/github-actions-cdk"
gh variable set AWS_REGION --body "eu-central-1"

# Set GitHub secret
gh secret set AWS_ACCOUNT_ID --body "197496953931"
```

### 4. Create KMS Key for Log Encryption (Recommended for Demos)

**Important:** For demo cycles where you deploy/destroy infrastructure multiple times, create the KMS key **once** and reuse it. This avoids creating/destroying keys repeatedly.

```bash
# Create KMS key (one-time setup)
aws kms create-key \
  --description "KMS key for NAT Gateway Alternative logs (persistent)" \
  --policy file://infra/policies/kms-flowlogs-policy.json \
  --region eu-central-1

# Note the KeyId from output, then create alias
aws kms create-alias \
  --alias-name alias/nat-alternative-logs \
  --target-key-id <KEY_ID_FROM_ABOVE> \
  --region eu-central-1
```

The config files (`cdk/config/test_config.py` and `cdk/config/prod_config.py`) are already set to use `alias/nat-alternative-logs` by default. If you use a different alias, update the config files.

**Why reuse keys?**
- ✅ Avoids $1.00 key creation cost per deployment
- ✅ Faster deployments (no key creation time)
- ✅ Keys persist across stack destroy/recreate cycles
- ✅ Best practice: KMS keys are long-lived resources

See `docs/kms-key-setup.md` for detailed instructions.

## What CDK Creates vs What You Create

### You Create (Prerequisites):
- ✅ GitHub Actions IAM role (`github-actions-cdk`)
- ✅ OIDC provider (one-time per AWS account)
- ✅ CDK bootstrap (one-time per account/region)
- ✅ **KMS key for log encryption** (recommended - create once, reuse always)

### CDK Creates (Infrastructure):
- ✅ VPC, subnets, route tables
- ✅ NAT instances with Auto Scaling Groups
- ✅ Elastic IPs
- ✅ Security groups
- ✅ IAM roles for EC2 instances and Lambda functions
- ✅ Lambda functions
- ✅ EventBridge rules
- ✅ CloudWatch Log Groups
- ✅ VPC Flow Logs
- ✅ Test probe instances
- ✅ All CloudFormation stack resources

## Key Differences from Terraform

| Aspect | Terraform | CDK |
|--------|-----------|-----|
| **State Storage** | Manual S3 bucket | CloudFormation (managed by AWS) |
| **State Locking** | Manual DynamoDB table | CloudFormation (built-in) |
| **Deployment Role** | Separate role with assume-role chain | Direct permissions on GitHub Actions role |
| **Credentials** | IAM user with access keys | OIDC (no static credentials) |
| **Bootstrap** | Manual S3/DynamoDB setup | `cdk bootstrap` command |
| **Asset Storage** | N/A (Terraform manages code) | S3 bucket created by bootstrap |

## Verification

### Check CDK Bootstrap
```bash
# List CDK bootstrap resources
aws cloudformation describe-stacks \
  --stack-name CDKToolkit \
  --region eu-central-1
```

### Check GitHub Actions Role
```bash
# Verify role exists
aws iam get-role --role-name github-actions-cdk

# Verify policy attached
aws iam get-role-policy \
  --role-name github-actions-cdk \
  --policy-name GitHubActionsCDKDeployment
```

### Test Deployment
```bash
# Synthesize template
cdk synth --context environment=test

# Deploy (if ready)
cdk deploy --context environment=test
```

## Troubleshooting

### Bootstrap Already Exists
If bootstrap already exists, you'll see:
```
 ⏳  Bootstrapping environment aws://197496953931/eu-central-1...
CDKToolkit: creating CloudFormation changeset...
 ✅  Environment aws://197496953931/eu-central-1 bootstrapped (no changes).
```
This is normal - bootstrap is idempotent.

### Missing Permissions
If you see permission errors:
1. Verify GitHub Actions role has all required permissions
2. Check `infra/policies/github-actions-policy.json` includes CloudFormation permissions
3. Ensure role trust policy allows OIDC from your repository

### Stack Already Exists
If deploying to an existing stack:
- CDK will update the stack (no need to destroy first)
- Use `cdk diff` to preview changes
- Use `cdk destroy` to remove the stack

## Summary

**CDK requires LESS manual setup than Terraform:**
- ❌ No S3 bucket for state (CloudFormation manages state)
- ❌ No DynamoDB table for locking (CloudFormation handles this)
- ❌ No IAM user with static credentials (OIDC only)
- ❌ No separate deployment role (GitHub Actions role has direct permissions)
- ✅ Just bootstrap + GitHub Actions role + OIDC provider

**CDK is simpler because:**
- CloudFormation manages state automatically
- No need for state file management
- OIDC authentication (no static credentials)
- Bootstrap command handles asset storage setup
