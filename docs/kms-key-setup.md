# KMS Key Setup for Log Encryption

## Overview

KMS keys for log encryption should be **created once** and **reused** across multiple deployments. This avoids unnecessary key creation/destruction during demo cycles and reduces costs.

## Why Reuse KMS Keys?

- **Cost efficiency:** KMS key creation/deletion costs money; reuse avoids repeated charges
- **Demo cycles:** When deploying/destroying infrastructure multiple times, persistent keys prevent recreation
- **Best practice:** KMS keys are long-lived resources that should exist independently of application infrastructure
- **Performance:** Reusing keys is faster than creating new ones each time

## One-Time Setup

### 1. Create KMS Key (One-Time)

```bash
# Create KMS key with the policy
aws kms create-key \
  --description "KMS key for NAT Gateway Alternative logs (persistent)" \
  --policy file://infra/policies/kms-flowlogs-policy.json \
  --region eu-central-1

# Note the KeyId from the output, then create an alias
aws kms create-alias \
  --alias-name alias/nat-alternative-logs \
  --target-key-id <KEY_ID> \
  --region eu-central-1
```

### 2. Get the KMS Key ARN

```bash
# Get the key ARN
aws kms describe-key \
  --key-id alias/nat-alternative-logs \
  --region eu-central-1 \
  --query 'KeyMetadata.Arn' \
  --output text
```

### 3. Configuration Files (Already Set)

The config files (`cdk/config/test_config.py` and `cdk/config/prod_config.py`) are already configured to use the alias:

```python
logs_kms_key_alias: str = "alias/nat-alternative-logs"  # Already set by default
```

**No changes needed** - just create the key with the alias name above, and CDK will automatically use it.

Alternatively, if you prefer using the ARN directly:
```python
logs_kms_key_arn: str = "arn:aws:kms:eu-central-1:197496953931:key/<KEY_ID>"
logs_kms_key_alias: str = ""  # Clear alias if using ARN
```

## Using the Key in CDK

The CDK stack will:
- ✅ Use the existing KMS key if `logs_kms_key_arn` or `logs_kms_key_alias` is provided
- ✅ Create a new key only if both are empty (not recommended for demos)
- ✅ **Never delete** the KMS key when destroying the stack
  - Keys referenced via ARN/alias are not managed by CDK (won't be deleted)
  - Keys created by CDK have `removal_policy=RETAIN` (preserved on stack destroy)

**Important:** When using `logs_kms_key_alias`, the key must exist **before** running `cdk synth` or `cdk deploy`. CDK will look up the key during synthesis.

## Configuration Options

### Option 1: Use Key ARN (Recommended)
```python
logs_kms_key_arn: str = "arn:aws:kms:eu-central-1:197496953931:key/12345678-1234-1234-1234-123456789abc"
```

### Option 2: Use Key Alias
```python
logs_kms_key_alias: str = "alias/nat-alternative-logs"
```

### Option 3: Let CDK Create (Not Recommended for Demos)
```python
logs_kms_key_arn: str = ""  # CDK will create a new key each time
```

## Verification

After deployment, verify the key is being used:

```bash
# Check CloudWatch log groups are encrypted with your key
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/vpc/nat-alternative" \
  --region eu-central-1 \
  --query 'logGroups[].{Name:logGroupName,KmsKeyId:kmsKeyId}'
```

## Key Management

- **Create once:** Run the setup commands above one time
- **Reuse always:** The same key will be used for all deployments
- **Manual cleanup:** If you need to delete the key, do it manually after all infrastructure is destroyed:
  ```bash
  # Schedule key deletion (30 day waiting period)
  aws kms schedule-key-deletion \
    --key-id alias/nat-alternative-logs \
    --pending-window-in-days 30
  ```

## Cost Considerations

- **Key creation:** ~$1.00 per key (one-time)
- **Key storage:** ~$1.00/month per key
- **Key usage:** Free for first 20,000 requests/month, then $0.03 per 10,000 requests

By reusing a single key, you pay:
- ✅ $1.00 one-time creation cost
- ✅ $1.00/month storage
- ❌ No repeated creation costs during demo cycles

## Troubleshooting

### Key Not Found
If you see errors about the key not existing:
1. Verify the key exists: `aws kms describe-key --key-id alias/nat-alternative-logs`
2. Check the ARN/alias in config files matches the actual key
3. Ensure you're using the correct region (eu-central-1)

### Permission Errors
If CDK can't use the key:
1. Verify the key policy allows CloudWatch Logs service
2. Check the key policy in `infra/policies/kms-flowlogs-policy.json`
3. Ensure the account ID in the policy matches your account (197496953931)
