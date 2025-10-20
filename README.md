# Cloud SysAdmin Technical Exercise — 2025-09

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

- **Architecture diagram** illustrating all components and network flow.  
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

## 🗺️ Architecture Diagram

```mermaid
flowchart TD

subgraph AZ1["Availability Zone 1"]
    EC2A[NAT EC2 Instance A<br> (ASG Member)]
    PVA[Private Subnet A]
end

subgraph AZ2["Availability Zone 2"]
    EC2B[NAT EC2 Instance B<br> (ASG Member)]
    PVB[Private Subnet B]
end

IGW[Internet Gateway]
NLB[NLB (Cross-AZ)]
CW[CloudWatch + Alarms]
RTB[Private Route Tables]

PVA --> RTB
PVB --> RTB
RTB --> NLB
NLB --> EC2A
NLB --> EC2B
EC2A --> IGW
EC2B --> IGW

CW -.-> EC2A
CW -.-> EC2B
````

**Description of Components**

* **EC2 NAT Instances (A & B):**
  Custom AMIs with iptables masquerade enabled, running in Auto Scaling Group.
* **NLB (Network Load Balancer):**
  Provides static IP endpoints and cross-AZ routing.
* **Route Tables:**
  Private subnets forward all `0.0.0.0/0` traffic to NLB.
* **Internet Gateway:**
  Provides outbound connectivity to the internet.
* **CloudWatch:**
  Health checks, alarms, and auto-recovery for failed instances.

---

## 🧮 Project Structure

```bash
.
├── README.md
├── docs/
│   ├── architecture-diagram.mmd
│   ├── design-notes.md
│   └── github-actions-pipeline.md
├── infra/
│   ├── backend.tf
│   ├── backend-test.hcl
│   ├── backend-prod.hcl
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── scripts/
│   │   └── verify_nat.sh
│   └── infra/policies/
│       ├── terraform-role-trust.json
│       ├── nat-alternative-terraform-policy.json
│       ├── terraform-user-policy.json
│       ├── terraform-state-policy.json
│       ├── kms-flowlogs-policy.json
│       ├── github-actions-trust.json
│       └── github-actions-policy.json
└── .github/workflows/                # currently disabled while iterating locally
```
## 🚀 Quick Start (manual execution)
> Shortcut: `./infra/scripts/bootstrap.sh --profile terraform-role --env test` will reapply policies (unless `--skip-iam`) and run Terraform plan/apply with the correct backend/var files.


1. **Configure AWS profiles**
   - Add the `terraform` IAM user and your admin keys to `~/.aws/credentials`.
   - Add the assume-role profile to `~/.aws/config`:
     ```ini
     [profile terraform-role]
     role_arn = arn:aws:iam::165820787764:role/nat-alternative-terraform
     source_profile = terraform
     external_id = terraform-nat-build
     region = eu-central-1
     ```
2. **Seed IAM/KMS/S3/DynamoDB (one-time per account)**
   - Review `infra/policies/*.json`, adjust ARNs if needed, then run the commands in `docs/terraform-role-setup.md`.
3. **Bootstrap Terraform remote state**
   ```bash
   cd infra
   AWS_PROFILE=terraform-role terraform init -migrate-state \
     -backend-config=backend-test.hcl
   ```
4. **Plan / Apply**
   ```bash
   AWS_PROFILE=terraform-role terraform plan \
     -var-file=environments/test/vars.tfvars

   AWS_PROFILE=terraform-role terraform apply \
     -var-file=environments/test/vars.tfvars
   ```
5. **Validate deployment**
   ```bash
   AWS_PROFILE=terraform-role ./scripts/verify_nat.sh test
   ```

Swap in the production backend (`backend-prod.hcl`) and var file when promoting.

## 🎬 Demo & Automation Roadmap

- **Terraform-first demo** – use Terraform to deploy the full stack in a sandbox account, then run `verify_nat.sh` to confirm NAT health and routing.
- **Traffic probes** – extend probe user-data or SSM automation to generate curl/iperf traffic, publish latency/packet-loss metrics, and store traces for demo dashboards.
- **Lambdas & maintenance** – implement the Lambda functions described in `docs/design-notes.md` (`nat-health-probe`, `nat-route-failover`, `config-guard`, etc.) to automate failover, configuration drift checks, and probe orchestration.
- **Suggested demo flow**
  1. `terraform apply` in a clean account.
  2. Run `verify_nat.sh`, show CloudWatch metrics/flow logs.
  3. Trigger synthetic traffic via probes; present dashboards/alerts.
  4. Manually stop a NAT instance and demonstrate Lambda-driven failover once implemented.

See `docs/design-notes.md` (§12) for the extended automation backlog and Lambda roadmap.


---

## 🚀 Planned Work (Epics and Tasks)

### Epic 1 — Architecture & Design

* [ ] Analyze AWS components suitable for NAT alternative (EC2, ASG, NLB, Route Tables, IAM).
* [ ] Create **multi-AZ design** with fault tolerance.
* [ ] Document routing logic and failover mechanism.
* [ ] Draw initial architecture diagram (Mermaid / Draw.io).

### Epic 2 — Infrastructure as Code (IaC)

* [ ] Implement Terraform or Pulumi stack.
* [ ] Create parameterized **test** and **prod** environments.
* [ ] Automate EC2 image creation (Packer optional).
* [ ] Integrate health checks and dynamic routes.

### Epic 3 — CI/CD Pipeline

* [ ] Set up GitHub Actions workflow.
* [ ] Lint and validate infrastructure definitions.
* [ ] Deploy to **test** environment on push.
* [ ] Manual approval step for **prod** deployment.

### Epic 4 — Monitoring & Security

* [ ] Add CloudWatch metrics and alarms for instance health.
* [ ] Enable VPC Flow Logs and log rotation.
* [ ] Configure IAM roles and least privilege policies.
* [ ] Document operational runbook (failover, maintenance).

### Epic 5 — Documentation & Review

* [ ] Write component explanations and trade-offs.
* [ ] Include cost and scalability considerations.
* [ ] Create `docs/design-notes.md` for reviewers.
* [ ] Record demo or screenshots (optional).

---

## ⚙️ Example GitHub Actions Pipelines

<details>
<summary><b>✅ CI — Lint & Validate Terraform (test.yml)</b></summary>

```yaml
name: CI Validate Infra

on:
  push:
    branches: [ main, dev ]
  pull_request:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        run: terraform init infra/

      - name: Terraform Validate
        run: terraform validate infra/
```

</details>

<details>
<summary><b>🚀 Deploy to Test Environment (deploy-test.yml)</b></summary>

```yaml
name: Deploy Test

on:
  push:
    branches: [ dev ]

jobs:
  deploy-test:
    runs-on: ubuntu-latest
    environment: test

    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        run: terraform init -backend-config=environments/test/backend.tfvars

      - name: Terraform Plan
        run: terraform plan -var-file=environments/test/vars.tfvars

      - name: Terraform Apply
        run: terraform apply -auto-approve -var-file=environments/test/vars.tfvars
```

</details>

<details>
<summary><b>🏁 Deploy to Production with Approval (deploy-prod.yml)</b></summary>

```yaml
name: Deploy Production

on:
  workflow_dispatch:

jobs:
  deploy-prod:
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://aws.amazon.com

    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        run: terraform init -backend-config=environments/prod/backend.tfvars

      - name: Terraform Plan
        run: terraform plan -var-file=environments/prod/vars.tfvars

      - name: Manual Approval
        uses: trstringer/manual-approval@v1
        with:
          approvers: vitalii-perminov

      - name: Terraform Apply
        run: terraform apply -auto-approve -var-file=environments/prod/vars.tfvars
```

</details>

---

## 🧠 Implementation Timeline

| Day | Focus                        | Deliverables                            |
| --- | ---------------------------- | --------------------------------------- |
| 1–2 | Architecture & Documentation | Diagram, component design, trade-offs   |
| 3–4 | IaC Implementation           | Terraform/Pulumi stack with scripts     |
| 5   | CI/CD Setup                  | GitHub Actions workflows                |
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
