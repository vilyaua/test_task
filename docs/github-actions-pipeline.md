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
              "repo:vilyaua/test_task:environment:*",
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

  The trust policy template is stored at `infra/policies/github-actions-trust.json`. Update the repo/branch filters if required, then apply it with:

  ```bash
  aws iam create-role \
    --role-name github-actions-terraform \
    --assume-role-policy-document file://infra/policies/github-actions-trust.json \
    --description "GitHub Actions OIDC role for Terraform" || true

  aws iam update-assume-role-policy \
    --role-name github-actions-terraform \
    --policy-document file://infra/policies/github-actions-trust.json
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

  The inline policy template lives at `infra/policies/github-actions-policy.json`. Adjust the allowed actions as needed, then attach it:

  ```bash
  aws iam put-role-policy \
    --role-name github-actions-terraform \
    --policy-name GitHubActionsTerraformAccess \
    --policy-document file://infra/policies/github-actions-policy.json
  ```

- **GitHub variables:** Store the role ARN and default region as repository-level variables (`AWS_ROLE_TO_ASSUME`, `AWS_REGION`).

  ```bash
  gh variable set AWS_ROLE_TO_ASSUME --body "arn:aws:iam::165820787764:role/github-actions-terraform"
  gh variable set AWS_REGION --body "eu-central-1"
  ```

## 2. Workflow
- **`prepare-for-demo.yml` (push to `main`, PR, or manual dispatch):**
  - Validates Terraform on every push/PR touching infra/docs, then exposes a manual demo path when triggered with `workflow_dispatch`.
  - Jobs:
    - `validate`: runs fmt, tflint, tfsec, `terraform validate`, and `terraform plan` (test var-file) with artifacts.
    - `Demo (apply)`: gated by the `demo-<env>` environment. Once approved, plans/applies against the selected env, runs verification script, and gathers probe logs.
    - `Demo (destroy)`: optional teardown gated by the `teardown-<env>` environment when `auto_destroy=true`.

  ```yaml
  # .github/workflows/prepare-for-demo.yml
  jobs:
    validate:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: hashicorp/setup-terraform@v3
          with:
            terraform_version: 1.13.3
        - uses: aws-actions/configure-aws-credentials@v4
          with:
            role-to-assume: ${{ vars.AWS_ROLE_TO_ASSUME }}
            aws-region: ${{ vars.AWS_REGION }}
        - run: terraform init -input=false -backend-config=backend-test.hcl
          working-directory: infra
        - run: terraform plan -var-file=environments/test/vars.tfvars -out=tfplan
          working-directory: infra
    demo_apply:
      environment: demo-${{ github.event.inputs.environment }}
      needs: validate
      if: github.event_name == 'workflow_dispatch' && github.event.inputs.run_demo == 'true'
      env:
        TERRAFORM_ENV: ${{ github.event.inputs.environment }}
      steps:
        - uses: actions/checkout@v4
        - uses: hashicorp/setup-terraform@v3
          with:
            terraform_version: 1.13.3
        - uses: aws-actions/configure-aws-credentials@v4
          with:
            role-to-assume: ${{ vars.AWS_ROLE_TO_ASSUME }}
            aws-region: ${{ vars.AWS_REGION }}
        - run: terraform apply -auto-approve tfplan
          working-directory: infra
        - run: ./scripts/verify_nat.sh ${{ env.TERRAFORM_ENV }}
          working-directory: infra
    demo_destroy:
      environment: teardown-${{ github.event.inputs.environment }}
      needs: demo_apply
      if: github.event_name == 'workflow_dispatch' && github.event.inputs.run_demo == 'true' && github.event.inputs.auto_destroy == 'true'
      env:
        TERRAFORM_ENV: ${{ github.event.inputs.environment }}
      steps:
        - uses: actions/checkout@v4
        - uses: hashicorp/setup-terraform@v3
          with:
            terraform_version: 1.13.3
        - uses: aws-actions/configure-aws-credentials@v4
          with:
            role-to-assume: ${{ vars.AWS_ROLE_TO_ASSUME }}
            aws-region: ${{ vars.AWS_REGION }}
        - run: terraform destroy -auto-approve -var-file=environments/${{ env.TERRAFORM_ENV }}/vars.tfvars
          working-directory: infra
  ```

  Approvals: add yourself/teams as required reviewers under the `demo-*` and `teardown-*` environments (`Settings → Environments`). After the `validate` job succeeds, dispatchers approve the environment gates directly in the Actions UI.

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
