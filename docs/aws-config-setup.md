# AWS Config Setup for CDK

This document describes the AWS CLI configuration profile for CDK deployments.

## CDK Profile Configuration

A profile named `cdk` has been added to `~/.aws/config` with the following settings:

```ini
[profile cdk]
region = eu-central-1
output = json
```

## Usage

### With AWS CLI
```bash
# Use the CDK profile for AWS CLI commands
aws ec2 describe-instances --profile cdk

# Or set as default for the session
export AWS_PROFILE=cdk
aws ec2 describe-instances
```

### With CDK
```bash
# CDK will use the default profile or AWS_PROFILE environment variable
export AWS_PROFILE=cdk
cdk deploy --context environment=test

# Or specify profile explicitly in AWS CLI config
# CDK respects AWS_PROFILE environment variable
```

### With Environment Variables
```bash
# Set AWS credentials via environment variables (alternative to profiles)
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_DEFAULT_REGION=eu-central-1

# CDK will use these automatically
cdk deploy --context environment=test
```

## Account Information

- **Account ID:** 197496953931
- **Region:** eu-central-1
- **Profile Name:** cdk

## Credentials

The `~/.aws/config` file only contains profile settings. Credentials should be stored in `~/.aws/credentials`:

```ini
[cdk]
aws_access_key_id = YOUR_ACCESS_KEY_ID
aws_secret_access_key = YOUR_SECRET_ACCESS_KEY
```

Or use IAM roles, temporary credentials, or other authentication methods.

## Verification

Test the profile configuration:

```bash
# Verify profile works
aws sts get-caller-identity --profile cdk

# Should return:
# {
#     "UserId": "...",
#     "Account": "197496953931",
#     "Arn": "arn:aws:iam::197496953931:user/..."
# }
```

## Next Steps

1. Add credentials to `~/.aws/credentials` for the `cdk` profile
2. Bootstrap CDK: `cdk bootstrap aws://197496953931/eu-central-1`
3. Deploy infrastructure: `cdk deploy --context environment=test`
