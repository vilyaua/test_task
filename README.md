# Cloud SysAdmin Technical Exercise — 2025-10

## Exercise: Design a Highly Available AWS-Based NAT Gateway Alternative

### Overview
The goal of this exercise is to **design and describe a highly available system in AWS** that provides functionality similar to a Managed NAT Gateway — **allowing outbound connections from private subnets to the internet while blocking unsolicited inbound traffic.**

This project is part of a **technical assessment** focused on architectural reasoning, operational excellence, and automation best practices.

---

## 🧩 Requirements

1. **Outbound connectivity:**  
   Private subnets must be able to initiate outbound connections to the internet.
2. **Inbound security:**  
   Prevent unsolicited inbound connections from the internet.
3. **High availability:**  
   Fault-tolerant design spanning multiple **Availability Zones**.
4. **Scalability:**  
   Support increasing workloads gracefully.
5. **Monitoring and alerting:**  
   Include metrics, logs, and alerts to detect failures or performance issues.
6. **Security best practices:**  
   Use IAM roles, least privilege, and encrypted communications.
7. **Cost efficiency and operational simplicity:**  
   Minimize operational overhead without compromising availability.

---

## 📦 Deliverables

- **High-level component explanation** (bulleted, concise).  
- **Optional:**  
  - Pseudo-code or IaC snippets (e.g., failover automation, routing logic).  
  - Scripts or GitHub Actions for deployment and validation.  

---

## 🧮 Evaluation Criteria

- Clarity of design and ability to communicate trade-offs.  
- How effectively the system addresses **availability, scalability, and security**.  
- Creativity in leveraging AWS native services (while **avoiding Managed NAT Gateway**).  
- Practicality — how easily it can be implemented and maintained.

---

## 🧮 Project Structure

```bash
.
├── README.md
├── app.py                           # CDK app entry point
├── cdk.json                         # CDK configuration
├── requirements.txt                 # Python dependencies
├── docs/
│   ├── design-notes.md
│   └── deploy-and-destroy-workflow.md
├── cdk/
│   ├── app.py                       # CDK app entry point
│   ├── config/
│   │   ├── test_config.py           # Test environment config
│   │   └── prod_config.py           # Production environment config
│   └── infra/
│       └── nat_stack.py             # Main CDK stack
├── infra/
│   ├── lambda/                      # Lambda function source code
│   │   ├── nat_asg_hook/
│   │   ├── log_collector/
│   │   └── demo_health/
│   └── scripts/
│       └── verify_nat.sh            # Deployment verification script
└── .github/workflows/
    └── deploy-and-destroy.yml        # CDK deploy/destroy workflow
```

## 🔀 Branching & Release Flow

- `development` is the day-to-day integration branch; small fixes can be pushed directly, larger efforts land via `feature/*` pull requests.
- `main` remains the production source of truth. Protect it so only reviewed PRs from `development` can merge, and require your approval before release.
- Feature branches are created from `development`, reviewed with focused PRs, and squashed back into `development`.
- Promote to production by raising a PR from `development` to `main`, then running CDK deploy from `main` after approval.

## 🚀 Quick Start (manual execution)

### Prerequisites

#### One-Time Setup (Per AWS Account/Region)

1. **Bootstrap CDK** (creates S3 bucket for assets and IAM roles for CloudFormation)
   ```bash
   cdk bootstrap aws://197496953931/eu-central-1
   ```
   This automatically creates:
   - S3 bucket for CDK assets (templates, Lambda code)
   - IAM roles for CloudFormation operations
   - ECR repositories (if using Docker assets)

2. **Create GitHub Actions IAM Role** (for CI/CD)
   ```bash
   # Create OIDC provider (one-time per AWS account)
   aws iam create-open-id-connect-provider \
     --url https://token.actions.githubusercontent.com \
     --client-id-list sts.amazonaws.com \
     --thumbprint-list cf23df2207d99a74fbe169e3eba035e633b65d94

   # Create IAM role
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

3. **Configure GitHub Variables**
   ```bash
   gh variable set AWS_ROLE_TO_ASSUME --body "arn:aws:iam::197496953931:role/github-actions-cdk"
   gh variable set AWS_REGION --body "eu-central-1"
   gh secret set AWS_ACCOUNT_ID --body "197496953931"
   ```

#### Local Development Setup

1. **Install CDK CLI**
   ```bash
   npm install -g aws-cdk
   ```

2. **Install Python dependencies**

   Using `uv` (recommended, faster):
   ```bash
   # Install uv: https://github.com/astral-sh/uv
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Install dependencies
   uv pip install -r requirements.txt
   ```

   Or using `pip`:
   ```bash
   pip install -r requirements.txt
   ```

3. **Setup pre-commit hooks (recommended)**
   ```bash
   pre-commit install
   ```
   This ensures code is formatted and validated before commits. See `docs/pre-commit-setup.md` for details.
   
   **Skip hooks if needed:** `git commit --no-verify -m "message"` (use sparingly)

4. **Configure AWS credentials**
   - Set up AWS credentials via `~/.aws/credentials` or environment variables
   - Ensure you have permissions to create VPC, EC2, Lambda, IAM, CloudFormation resources

5. **Create KMS Key (Recommended for Demos)**
   ```bash
   # Create persistent KMS key (one-time, reuse across deployments)
   aws kms create-key \
     --description "KMS key for NAT Gateway Alternative logs" \
     --policy file://infra/policies/kms-flowlogs-policy.json \
     --region eu-central-1
   
   # Create alias (use the KeyId from above)
   aws kms create-alias \
     --alias-name alias/nat-alternative-logs \
     --target-key-id <KEY_ID> \
     --region eu-central-1
   ```
   The config files already reference `alias/nat-alternative-logs` by default. This key will be reused across all deployments, avoiding creation/destruction costs during demo cycles.

**See `docs/cdk-prerequisites.md` and `docs/kms-key-setup.md` for detailed setup instructions.**

### Deploy Infrastructure

1. **Synthesize CloudFormation template**
   ```bash
   cdk synth --context environment=test
   ```

2. **Deploy to test environment**
   ```bash
   cdk deploy --context environment=test
   ```

3. **Deploy to production environment**
   ```bash
   cdk deploy --context environment=prod
   ```

4. **Validate deployment**
   ```bash
   cd infra
   ./scripts/verify_nat.sh test
   ```

### Destroy Infrastructure

```bash
cdk destroy --context environment=test
```

**Note:** Test environment uses 2 Availability Zones with CIDR `10.0.0.0/16`. Production uses 3 Availability Zones with CIDR `10.1.0.0/16`. Adjust these in `cdk/config/test_config.py` and `cdk/config/prod_config.py` if they overlap with existing VPCs.

## 🎬 Demo & Automation Roadmap

- **CDK deployment demo** – use CDK to deploy the full stack in a sandbox account, then run `verify_nat.sh` to confirm NAT health and routing.
- **GitHub Actions workflow** – trigger the `Deploy and Destroy Infrastructure` workflow, choose the target environment, and optionally run demo verification. Resources are automatically destroyed at the end to save costs.
- **Traffic probes** – probe instances automatically validate NAT connectivity on startup and report to CloudWatch Logs.
- **Lambda automation** – NAT ASG hook Lambda automatically configures routes and EIPs when instances launch (see *Planned Lambda Automations* below).
- **Suggested demo flow**
  1. `cdk deploy --context environment=test` in a clean account.
  2. Run `verify_nat.sh test`, show CloudWatch metrics/flow logs.
  3. Check probe logs in CloudWatch Logs for connectivity validation.
  4. Manually stop a NAT instance and observe ASG replacement with Lambda-driven route configuration.
  5. (Optional) Use GitHub Actions workflow for automated deploy/demo/destroy:
     ```bash
     gh workflow run "Deploy and Destroy Infrastructure" \
       --field environment=test \
       --field run_demo=true
     ```

See `docs/design-notes.md` for the extended automation backlog and Lambda roadmap.


---

## 🚀 Planned Work (Epics and Tasks)

### Epic 1 — Architecture & Design

* [x] Analyze AWS components suitable for NAT alternative (EC2, ASG, NLB, Route Tables, IAM).
* [x] Create **multi-AZ design** with fault tolerance.
* [x] Document routing logic and failover mechanism.

### Epic 2 — Infrastructure as Code (IaC)

* [x] Implement AWS CDK (Python) stack.
* [x] Create parameterized **test** and **prod** environments.
* [x] Automate EC2 image creation (using latest Amazon Linux 2023).
* [x] Integrate health checks and dynamic routes via Lambda automation.

### Epic 3 — CI/CD Pipeline

* [x] Set up GitHub Actions workflow.
* [x] Lint and validate infrastructure definitions.
* [x] Deploy to **test** environment on push.
* [ ] Manual approval step for **prod** deployment.

### Epic 4 — Monitoring & Security

* [x] Add CloudWatch metrics and alarms for instance health.
* [x] Enable VPC Flow Logs and log rotation.
* [x] Configure IAM roles and least privilege policies.
* [x] Document operational runbook (failover, maintenance).

### Epic 5 — Documentation & Review

* [x] Write component explanations and trade-offs.
* [ ] Include cost and scalability considerations.
* [x] Create `docs/design-notes.md` for reviewers.
* [ ] Record demo or screenshots (optional).

---

## ⚙️ CI/CD Workflows

- **Deploy and Destroy (`.github/workflows/deploy-and-destroy.yml`)** ⭐ **Recommended**
  - Simple workflow that deploys infrastructure using CDK, optionally runs demo/verification, and **always destroys resources** to save costs.
  - Perfect for quick validation and testing without leaving resources running.
  - Can be triggered manually with environment selection (`test` or `prod`) and optional demo step.
  - See `docs/deploy-and-destroy-workflow.md` for detailed usage instructions.

## 🧪 Planned Lambda Automations

- `nat-health-probe` — executes scheduled connectivity checks from probe instances and publishes CloudWatch metrics/alarms when outbound traffic fails.
- `nat-route-failover` — reacts to health alarms by shifting private subnet routes to the healthy NAT instance and re-associating elastic IPs if needed.
- `config-guard` — watches for configuration drift (routes, security groups, ASG settings) and either auto-remediates or raises incidents.
- `probe-controller` — coordinates lifecycle of lightweight probe instances/SSM automations used by the demo workflow and upcoming synthetic tests.

## 🧠 Implementation Timeline

| Day | Focus                        | Deliverables                            |
| --- | ---------------------------- | --------------------------------------- |
| 1–2 | Architecture & Documentation | Component design, trade-offs   |
| 3–4 | IaC Implementation           | Terraform/Pulumi stack with scripts     |
| 5   | CI/CD Setup                  | Prepare for Demo GitHub Actions workflow |
| 6   | Testing & Review             | Validation, cost analysis, final README |

---

## 🧰 Suggested AWS Components

* **EC2 NAT Instances** (custom AMI or Amazon Linux)
* **Auto Scaling Group (ASG)** for HA and resilience
* **Elastic IPs or NLB** for static outbound IP
* **VPC Route Tables** configured for outbound forwarding
* **CloudWatch** for monitoring and metrics
* **S3 + IAM Roles** for logging and automation
* **SSM (AWS Systems Manager)** for remote patching and updates

---

**Author:** Vitalii Perminov
**Date:** October 2025
**Location:** Vélez-Málaga, Spain

```

---
