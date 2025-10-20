#!/usr/bin/env bash
set -euo pipefail

#./infra/scripts/bootstrap.sh --profile terraform-role --skip-iam --env test

usage() {
  cat <<'USAGE'
Usage: $0 [--profile PROFILE] [--region REGION] [--env test|prod]
          [--state-bucket NAME] [--lock-table NAME]
          [--kms-key-id KEYID] [--create-kms-key]
          [--skip-iam] [--apply]

Options:
  --profile PROFILE     AWS CLI profile to use (default: terraform-role)
  --region REGION       AWS region (default: eu-central-1)
  --env ENV             Terraform environment (test|prod) (default: test)
  --state-bucket NAME   S3 bucket for Terraform state (default: terraform-state-ravenpack)
  --lock-table NAME     DynamoDB table for Terraform locks (default: terraform-locks)
  --kms-key-id KEYID    Existing KMS key ID for flow logs (enables rotation)
  --create-kms-key      Create a new KMS key using policies/kms-flowlogs-policy.json
  --skip-iam            Skip reapplying IAM/KMS/S3 policies
  --apply               Run 'terraform apply -auto-approve' after plan
  --help                Show this message

The script expects policy templates under infra/policies/ and backend
config files named backend-<env>.hcl.
USAGE
}

PROFILE="terraform-role"
REGION="eu-central-1"
ENVIRONMENT="test"
STATE_BUCKET="terraform-state-ravenpack"
LOCK_TABLE="terraform-locks"
KMS_KEY_ID=""
CREATE_KMS=false
SKIP_IAM=false
RUN_APPLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --state-bucket) STATE_BUCKET="$2"; shift 2 ;;
    --lock-table) LOCK_TABLE="$2"; shift 2 ;;
    --kms-key-id) KMS_KEY_ID="$2"; shift 2 ;;
    --create-kms-key) CREATE_KMS=true; shift ;;
    --skip-iam) SKIP_IAM=true; shift ;;
    --apply) RUN_APPLY=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required for this script" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
POLICY_DIR="$PWD/policies"

aws_cmd() {
  AWS_PROFILE="$PROFILE" AWS_DEFAULT_REGION="$REGION" aws "$@"
}

apply_policies() {
  echo "Reapplying IAM/KMS/S3 policies using profile $PROFILE in $REGION..."

  aws_cmd iam put-user-policy \
    --user-name terraform \
    --policy-name TerraformAssumeRoleOnly \
    --policy-document file://"$POLICY_DIR/terraform-user-policy.json"

  aws_cmd iam create-role \
    --role-name nat-alternative-terraform \
    --assume-role-policy-document file://"$POLICY_DIR/terraform-role-trust.json" \
    --description "Terraform role for NAT alternative deployment" \
    --max-session-duration 10800 || true

  aws_cmd iam update-assume-role-policy \
    --role-name nat-alternative-terraform \
    --policy-document file://"$POLICY_DIR/terraform-role-trust.json"

  aws_cmd iam put-role-policy \
    --role-name nat-alternative-terraform \
    --policy-name TerraformNATPolicy \
    --policy-document file://"$POLICY_DIR/nat-alternative-terraform-policy.json"

  aws_cmd s3api put-bucket-policy \
    --bucket "$STATE_BUCKET" \
    --policy file://"$POLICY_DIR/terraform-state-policy.json"

  if [[ "$CREATE_KMS" == true ]]; then
    echo "Creating new KMS key for flow logs..."
    key_json=$(aws_cmd kms create-key \
      --description "KMS key for NAT flow logs" \
      --key-usage ENCRYPT_DECRYPT \
      --policy file://"$POLICY_DIR/kms-flowlogs-policy.json" \
      --output json)
    KMS_KEY_ID=$(echo "$key_json" | jq -r '.KeyMetadata.KeyId')
    echo "Created KMS key: $KMS_KEY_ID"
  fi

  if [[ -n "$KMS_KEY_ID" ]]; then
    aws_cmd kms enable-key-rotation \
      --key-id "$KMS_KEY_ID"
  else
    echo "NOTE: Skipping KMS key rotation (no --kms-key-id provided)."
  fi
}

run_terraform() {
  local backend="backend-${ENVIRONMENT}.hcl"
  local tfvars="environments/${ENVIRONMENT}/vars.tfvars"

  if [[ ! -f "$backend" ]]; then
    echo "Backend config $backend not found" >&2
    exit 1
  fi
  if [[ ! -f "$tfvars" ]]; then
    echo "Variable file $tfvars not found" >&2
    exit 1
  fi

  echo "Terraform init (backend: $backend, profile: $PROFILE)..."
  AWS_PROFILE="$PROFILE" AWS_REGION="$REGION" terraform init -migrate-state \
    -backend-config="$backend"

  echo "Terraform plan (vars: $tfvars)..."
  AWS_PROFILE="$PROFILE" AWS_REGION="$REGION" terraform plan \
    -var-file="$tfvars"

  if [[ "$RUN_APPLY" == true ]]; then
    echo "Terraform apply..."
    AWS_PROFILE="$PROFILE" AWS_REGION="$REGION" terraform apply -auto-approve \
      -var-file="$tfvars"
  fi
}

main() {
  if [[ "$SKIP_IAM" == false ]]; then
    apply_policies
  else
    echo "Skipping IAM/KMS/S3 policy reapplication."
  fi

  run_terraform

  echo "All steps completed."
}

main "$@"
