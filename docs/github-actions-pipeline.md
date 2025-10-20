# GitHub Actions CI/CD Blueprint

This guide outlines the GitHub Actions setup for validating, deploying, testing, and cleaning the NAT gateway alternative infrastructure while minimizing AWS spend.

## 1. Required AWS Integration
- **OIDC provider (run once per account):**

  ```bash
  aws iam create-open-id-connect-provider \
    --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list cf23df2207d99a74fbe169e3eba035e633b65d94
  ```

  If the provider already exists, AWS returns `EntityAlreadyExists`.

- **OIDC trust:** Create (or update) an IAM role (e.g., `github-actions-terraform`) that allows `sts:AssumeRoleWithWebIdentity` from `token.actions.githubusercontent.com` with conditions on your repository and branch (`repo:vilyaua/test_task:ref:refs/heads/main`).

  ```json
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Federated": "arn:aws:iam::165820787764:oidc-provider/token.actions.githubusercontent.com"
        },
        "Action": "sts:AssumeRoleWithWebIdentity",
        "Condition": {
          "StringLike": {
            "token.actions.githubusercontent.com:sub": [
              "repo:vilyaua/test_task:ref:refs/heads/*",
              "repo:vilyaua/test_task:ref:refs/tags/*",
              "repo:vilyaua/test_task:pull_request"
            ]
          },
          "StringEquals": {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
          }
        }
      }
    ]
  }
  ```

  ```bash
  cat > github-actions-trust.json <<'JSON'
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {
          "Federated": "arn:aws:iam::165820787764:oidc-provider/token.actions.githubusercontent.com"
        },
        "Action": "sts:AssumeRoleWithWebIdentity",
        "Condition": {
          "StringLike": {
            "token.actions.githubusercontent.com:sub": [
              "repo:vilyaua/test_task:ref:refs/heads/*",
              "repo:vilyaua/test_task:ref:refs/tags/*",
              "repo:vilyaua/test_task:pull_request"
            ]
          },
          "StringEquals": {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
          }
        }
      }
    ]
  }
  JSON

  aws iam create-role \
    --role-name github-actions-terraform \
    --assume-role-policy-document file://github-actions-trust.json \
    --description "GitHub Actions OIDC role for Terraform" || true

  aws iam update-assume-role-policy \
    --role-name github-actions-terraform \
    --policy-document file://github-actions-trust.json
  ```

- **Permissions:** Attach a policy that covers Terraform operations (VPC, EC2, ELB/NLB, Auto Scaling, Lambda, CloudWatch, SSM, IAM PassRole). Reuse or extend the deployment role from `docs/terraform-role-setup.md`.

  ```json
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
          "cloudwatch:*",
          "logs:*",
          "ssm:*",
          "iam:PassRole",
          "iam:CreateServiceLinkedRole"
        ],
        "Resource": "*"
      }
    ]
  }
  ```

  ```bash
  cat > github-actions-policy.json <<'JSON'
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
          "cloudwatch:*",
          "logs:*",
          "ssm:*",
          "iam:PassRole",
          "iam:CreateServiceLinkedRole"
        ],
        "Resource": "*"
      },
      {
        "Effect": "Allow",
        "Action": "sts:AssumeRole",
        "Resource": "arn:aws:iam::165820787764:role/nat-alternative-terraform"
      }
    ]
  }
  JSON

  aws iam put-role-policy \
    --role-name github-actions-terraform \
    --policy-name GitHubActionsTerraformAccess \
    --policy-document file://github-actions-policy.json
  ```

- **GitHub secrets:** Store the role ARN and default region as `AWS_ROLE_TO_ASSUME` and `AWS_REGION`.

  ```bash
  gh secret set AWS_ROLE_TO_ASSUME --body "arn:aws:iam::165820787764:role/github-actions-terraform"
  gh secret set AWS_REGION --body "us-east-1"
  ```

## 2. Workflows
1. **`terraform-validate.yml` (push + PR):**
   - `terraform fmt -check`, `tflint`, `tfsec`.
   - `terraform validate` with plugin caching.
   - `terraform plan -var-file=environments/test/vars.tfvars` and upload the plan as an artifact + PR comment.

   ```yaml
   # .github/workflows/terraform-validate.yml
   jobs:
     validate:
       runs-on: ubuntu-latest
       env:
         TF_PLUGIN_CACHE_DIR: ${{ runner.temp }}/.terraform-cache
       steps:
         - uses: actions/checkout@v4
         - uses: hashicorp/setup-terraform@v3
           with:
             terraform_version: 1.13.3
         - uses: aws-actions/configure-aws-credentials@v4
           with:
             role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}
             aws-region: ${{ secrets.AWS_REGION }}
         - run: terraform init -input=false
           working-directory: infra
         - run: terraform plan -var-file=environments/test/vars.tfvars -out=tfplan
           working-directory: infra
   ```

2. **`terraform-deploy.yml` (main + manual dispatch):**
   - Assume the AWS role via OIDC, run `init`, `plan`, `apply`.
   - After apply, execute NAT connectivity probes (see Section 3).
   - Upload logs and metrics; fail the job if probes fail.

   ```yaml
   # .github/workflows/terraform-deploy.yml
   jobs:
     deploy:
       runs-on: ubuntu-latest
       env:
         TF_VAR_aws_profile: ""
         TARGET_ENV: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || 'test' }}
       steps:
         - uses: actions/checkout@v4
         - uses: hashicorp/setup-terraform@v3
         - uses: aws-actions/configure-aws-credentials@v4
           with:
             role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}
             aws-region: ${{ secrets.AWS_REGION }}
         - run: terraform apply -input=false -auto-approve tfplan
           working-directory: infra
         - run: ./scripts/verify_nat.sh "${TARGET_ENV}"
           working-directory: infra
   ```

3. **`terraform-destroy.yml` (nightly + manual):**
   - Runs `terraform destroy` with the same var-file to remove the test stack.
   - Also available via workflow dispatch for ad-hoc cleanup.

   ```yaml
   # .github/workflows/terraform-destroy.yml
   jobs:
     destroy:
       runs-on: ubuntu-latest
       env:
         TARGET_VAR_FILE: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.var_file || 'environments/test/vars.tfvars' }}
       steps:
         - uses: actions/checkout@v4
         - uses: aws-actions/configure-aws-credentials@v4
           with:
             role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}
             aws-region: ${{ secrets.AWS_REGION }}
         - run: terraform destroy -auto-approve -var-file=${{ env.TARGET_VAR_FILE }}
           working-directory: infra
   ```

Use workflow reuse (`workflow_call`) so `deploy` and `destroy` share init logic. Cache providers with `hashicorp/setup-terraform` and set `TF_PLUGIN_CACHE_DIR`.

## 3. Test Scenario Execution
- Launch lightweight probe instances in private subnets (t3.nano) using Terraform; user data runs outbound checks (curl to public endpoints, DNS lookups).
- Collect probe logs via SSM or CloudWatch Logs; the workflow downloads and inspects them for success markers.
- Optionally add synthetic tests (AWS SSM Session Manager automation or AWS Systems Manager RunCommand) triggered from the workflow for additional verification.

```bash
# infra/scripts/verify_nat.sh
./scripts/verify_nat.sh test
# Confirms NAT instances are running, private routes target their ENIs,
# and waits for probe instances to terminate gracefully.
```

## 4. Cost Control & Safety Nets
- Require manual approval (GitHub environment) before production deploys.
- Schedule nightly destroy to tear down idle stacks.
- Add AWS Budget alerts routed to Slack or email for unexpected charges.
