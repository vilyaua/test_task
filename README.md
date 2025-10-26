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
└── .github/workflows/
    └── prepare-for-demo.yml         # validation + optional demo pipeline
```

## 🔀 Branching & Release Flow

- `development` is the day-to-day integration branch; small fixes can be pushed directly, larger efforts land via `feature/*` pull requests.
- `main` remains the production source of truth. Protect it so only reviewed PRs from `development` can merge, and require your approval before release.
- Feature branches are created from `development`, reviewed with focused PRs, and squashed back into `development`.
- Promote to production by raising a PR from `development` to `main`, then running Terraform apply from `main` after approval.

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
`environments/prod/vars.tfvars` is already configured for three Availability Zones (`az_count = 3`) to meet HA requirements.
Each environment now uses a distinct CIDR block (`10.0.0.0/16` for test, `10.1.0.0/16` for prod); adjust these if they overlap with existing VPCs in your accounts.

## 🎬 Demo & Automation Roadmap

- **Terraform-first demo** – use Terraform to deploy the full stack in a sandbox account, then run `verify_nat.sh` to confirm NAT health and routing.
- **GitHub Actions demo button** – trigger the `Prepare for Demo` workflow, choose the target environment, and approve the `demo-*`/`teardown-*` environments to deploy, verify, and optionally destroy the stack automatically.
- **Traffic probes** – extend probe user-data or SSM automation to generate curl/iperf traffic, publish latency/packet-loss metrics, and store traces for demo dashboards.
- **Lambdas & maintenance** – implement automation functions (see *Planned Lambda Automations* below) to keep routing healthy, detect drift, and orchestrate probes.
- **Suggested demo flow**
  1. `terraform apply` in a clean account.
  2. Run `verify_nat.sh`, show CloudWatch metrics/flow logs.
  3. Trigger synthetic traffic via probes; present dashboards/alerts.
  4. Manually stop a NAT instance and demonstrate Lambda-driven failover once implemented.
  5. (Optional) Kick off the full CI + demo flow from the CLI:
     ```bash
     gh workflow run "Prepare for Demo" \
       --ref main \
       --field run_demo=true \
       --field environment=test \
       --field auto_destroy=true
     ```
     Approve `demo-test` and `teardown-test` when prompted in the Actions UI.

See `docs/design-notes.md` (§12) for the extended automation backlog and Lambda roadmap.


---

## 🚀 Planned Work (Epics and Tasks)

### Epic 1 — Architecture & Design

* [x] Analyze AWS components suitable for NAT alternative (EC2, ASG, NLB, Route Tables, IAM).
* [x] Create **multi-AZ design** with fault tolerance.
* [ ] Document routing logic and failover mechanism.
* [ ] Draw initial architecture diagram (Mermaid / Draw.io).

### Epic 2 — Infrastructure as Code (IaC)

* [x] Implement Terraform or Pulumi stack.
* [x] Create parameterized **test** and **prod** environments.
* [x] Automate EC2 image creation (Packer optional).
* [x] Integrate health checks and dynamic routes.

### Epic 3 — CI/CD Pipeline

* [x] Set up GitHub Actions workflow.
* [x] Lint and validate infrastructure definitions.
* [x] Deploy to **test** environment on push.
* [ ] Manual approval step for **prod** deployment.

### Epic 4 — Monitoring & Security

* [x] Add CloudWatch metrics and alarms for instance health.
* [x] Enable VPC Flow Logs and log rotation.
* [x] Configure IAM roles and least privilege policies.
* [ ] Document operational runbook (failover, maintenance).

### Epic 5 — Documentation & Review

* [x] Write component explanations and trade-offs.
* [ ] Include cost and scalability considerations.
* [x] Create `docs/design-notes.md` for reviewers.
* [ ] Record demo or screenshots (optional).

---

## ⚙️ CI/CD Workflow

- **Prepare for Demo (`.github/workflows/prepare-for-demo.yml`)**
  - Runs fmt, tflint, tfsec, and `terraform plan` on every push/PR that touches infra or docs.
  - When launched manually, pauses for `demo-*` and `teardown-*` environment approvals before applying or destroying demo stacks.
  - Captures plan artifacts and runs `infra/scripts/verify_nat.sh` plus probe log collection so reviewers have evidence of the deployment.
- See `docs/github-actions-pipeline.md` for the full YAML snippet and environment setup guidance.

## 🧪 Planned Lambda Automations

- `nat-health-probe` — executes scheduled connectivity checks from probe instances and publishes CloudWatch metrics/alarms when outbound traffic fails.
- `nat-route-failover` — reacts to health alarms by shifting private subnet routes to the healthy NAT instance and re-associating elastic IPs if needed.
- `config-guard` — watches for configuration drift (routes, security groups, ASG settings) and either auto-remediates or raises incidents.
- `probe-controller` — coordinates lifecycle of lightweight probe instances/SSM automations used by the demo workflow and upcoming synthetic tests.

## 🧠 Implementation Timeline

| Day | Focus                        | Deliverables                            |
| --- | ---------------------------- | --------------------------------------- |
| 1–2 | Architecture & Documentation | Diagram, component design, trade-offs   |
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
