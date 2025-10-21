# Activity Log

This log captures significant repository activities handled by the agent. Timestamps are recorded in UTC and durations are approximate, based on interactive session time.

| Date (UTC)        | Activity                                   | Details                                                                                   | Time Spent |
|-------------------|--------------------------------------------|-------------------------------------------------------------------------------------------|------------|
| 2025-10-19 17:20  | Authored contributor guide `AGENTS.md`     | Reviewed existing docs (`README.md`, `docs/design-notes.md`) and drafted repository guidelines. | ~25 min    |
| 2025-10-19 17:47  | Installed AWS CLI tooling                  | Used Homebrew to install `awscli` (v2.31.18) with prerequisites (`openssl@3`, `python@3.13`). | ~5 min     |
| 2025-10-19 18:15  | Documented Terraform IAM role setup        | Added `docs/terraform-role-setup.md` with trust policy, permission, and provider configuration steps. | ~10 min    |
| 2025-10-19 18:30  | Clarified profile selection instructions   | Updated `docs/terraform-role-setup.md` with guidance on choosing AWS CLI/Terraform profiles. | ~5 min     |
| 2025-10-19 18:35  | Finalized Terraform role guidance          | Confirmed instructions in `docs/terraform-role-setup.md` meet requirements before infra work. | ~2 min     |
| 2025-10-19 18:40  | Built test environment Terraform configs   | Added VPC, subnet, and NAT instance Terraform for test env plus vars/outputs; `terraform fmt` run (validate blocked by plugin). | ~20 min    |
| 2025-10-19 18:42  | Documented test environment deployment     | Created `docs/test-environment-deploy.md` with init/plan/apply/destroy instructions and checks. | ~5 min     |
| 2025-10-19 18:52  | Fixed Terraform validation blockers        | Updated provider version, route resource, and ran `terraform validate` successfully (requires unsandboxed run for plugin sockets). | ~10 min    |
| 2025-10-19 18:58  | Integrated feature branch into main        | Created `feat-terraform-initial`, merged via PR #2 into `main` after review. | ~5 min     |
| 2025-10-19 19:04  | Ensured Terraform uses correct profile     | Added `aws_profile` variable with default `terraform`, updated provider config/docs, reran `terraform validate`. | ~8 min     |
| 2025-10-19 19:22  | Added repository-specific .gitignore       | Ignored Terraform state/cache, editor artifacts, and generated docs while keeping tracked env vars. | ~3 min     |
| 2025-10-19 19:23  | Prepared for push                          | Reviewed status after .gitignore update; ready to push latest documentation and infra changes. | ~2 min     |
| 2025-10-19 19:27  | Paused work                                | Session paused; no repository changes during this interval. | —          |
| 2025-10-19 20:10  | Captured test environment topology         | Added `docs/test-environment.mmd` Mermaid diagram and referenced it in deployment docs. | ~6 min     |
| 2025-10-19 20:13  | Fixed Mermaid syntax errors                | Adjusted `docs/test-environment.mmd` note syntax for compatibility with Mermaid renderer. | ~3 min     |
| 2025-10-19 20:20  | Outlined GitHub Actions pipeline           | Authored `docs/github-actions-pipeline.md` detailing validate/deploy/destroy workflows and OIDC integration. | ~7 min     |
| 2025-10-19 20:27  | Added NAT probe automation                  | Introduced probe instances/user data (`infra/test_probes.tf`), variables, and outputs plus doc updates. | ~12 min    |
| 2025-10-19 20:45  | Implemented GitHub Actions workflows        | Added Terraform validate/deploy/destroy workflows and verification script for NAT checks. | ~18 min    |
| 2025-10-19 20:48  | Added workflow documentation snippets       | Updated `docs/github-actions-pipeline.md` with YAML and script snippets for quick reference. | ~3 min     |
| 2025-10-19 20:56  | Documented AWS integration snippets         | Extended `docs/github-actions-pipeline.md` with trust policy, permissions, and secrets commands. | ~4 min     |
| 2025-10-19 20:58  | Added AWS CLI setup commands                | Documented role creation and policy attachment bash steps in `docs/github-actions-pipeline.md`. | ~2 min     |
| 2025-10-19 21:21  | Fixed workflow cache path                   | Updated Terraform workflows to use workspace cache instead of runner.temp to satisfy GitHub Actions parser. | ~2 min     |
| 2025-10-19 21:24  | Pinned tfsec action version                 | Updated `terraform-validate` workflow to use `aquasecurity/tfsec-action@v1.0.0`. | ~1 min     |
| 2025-10-19 21:27  | Ensured TF cache dirs exist in workflows    | Added `mkdir -p` and runner temp caching in Terraform workflows to avoid init failures. | ~2 min     |
| 2025-10-19 21:35  | Normalized Terraform var-file formatting    | Ran `terraform fmt` on `infra/environments/test/vars.tfvars` so CI fmt check passes. | ~1 min     |
| 2025-10-19 21:38  | Documented local validation steps           | Added `docs/local-development.md` describing fmt/lint/validate commands for contributors. | ~3 min     |
| 2025-10-19 21:50  | Added tfsec suppressions for NAT SG         | Annotated NAT security group egress with inline tfsec ignores and rationale. | ~2 min     |
| 2025-10-19 21:53  | Enabled VPC flow logs & updated probes      | Added CloudWatch flow logs resources, probe SG description, and doc note on tfsec. | ~5 min     |
| 2025-10-19 22:05  | Hardened flow log IAM policy and KMS key    | Scoped IAM resources, added KMS key policy, and ensured tfsec passes. | ~6 min     |
| 2025-10-19 22:38  | Reused existing KMS alias in Terraform      | Documented alias usage and wired `logs_kms_key_arn` variable for env-specific configuration. | ~2 min     |
| 2025-10-19 22:41  | Added OIDC permissions to workflows         | Granted `id-token` permissions for GitHub Actions AWS authentication. | ~1 min     |
| 2025-10-19 22:48  | Documented GitHub OIDC provider setup       | Added `aws iam create-open-id-connect-provider` to pipeline guide. | ~1 min     |
| 2025-10-19 23:14  | Added role update command to GH guide        | Included `update-assume-role-policy` example for existing Terraform role. | ~1 min     |
| 2025-10-19 23:23  | Expanded OIDC trust scope in docs            | Updated snippets to allow branches, tags, and PR tokens. | ~1 min     |
| 2025-10-19 23:29  | Added sts:AssumeRole permission to GH docs   | Ensured GitHub role can assume `nat-alternative-terraform`. | ~1 min     |
| 2025-10-19 23:38  | Added policy update note to GH docs         | Documented reusing `put-role-policy` for existing inline policy. | ~1 min     |
| 2025-10-20 00:27  | Clarified Terraform role trust policy       | Documented dual principals (user + GH Actions) and update command. | ~2 min     |
| 2025-10-20 00:46  | Added environment claim to GH trust docs    | Allowed `repo:...:environment:*` in trust policy snippets. | ~1 min     |
| 2025-10-20 00:53  | Extended Terraform role IAM permissions     | Added create role/policy actions so flow-log IAM resources can be managed. | ~1 min     |
| 2025-10-20 00:58  | Switched default Terraform region           | Set `aws_region` default to `eu-central-1` and validated configuration. | ~1 min     |
| 2025-10-20 02:02  | Paused development after AWS cleanup        | Manual teardown in progress; development halted until cleanup completes. | —          |
| 2025-10-20 07:09  | Restored default AWS profile behaviour      | Emptied `aws_profile` default so env-based auth works without extra vars. | ~1 min     |
| 2025-10-20 07:15  | Added S3 backend & workflow refinements     | Created `infra/backend.tf`, documented remote state, and updated CI pipelines to manual deploy/destroy flow. | ~6 min     |
| 2025-10-20 11:16  | Documented remote state IAM permissions      | Expanded role policy snippet to include S3/DynamoDB access for backend. | ~2 min     |
| 2025-10-20 11:40  | Disabled CI workflows & enhanced local docs  | Temporarily disabled GH Actions and expanded local setup guidance. | ~3 min     |
| 2025-10-20 18:27  | Clarified AWS profile setup                  | Updated local docs to use IAM user `terraform` as source profile. | ~2 min     |
| 2025-10-20 18:35  | Removed provider assume-role dependency      | Provider now uses supplied profile creds; updated docs accordingly. | ~2 min     |
| 2025-10-20 18:50  | Added backend config files                   | Created `infra/backend-test.hcl`/`backend-prod.hcl` and documented usage. | ~2 min     |
| 2025-10-20 19:05  | Added manual gates to demo workflow          | Updated `.github/workflows/terraform-validate.yml` to require approvals before demo apply/destroy stages. | ~3 min     |
| 2025-10-20 19:12  | Enabled demo job by default                  | Set `run_demo` input default to `true` so manual dispatch runs the demo unless explicitly disabled. | ~1 min     |
| 2025-10-20 19:24  | Swapped approval action implementation       | Replaced unavailable `uber/workflow-dispatch-wait-action` with `trstringer/manual-approval` and exposed `demo_approvers` input. | ~3 min     |
| 2025-10-20 19:32  | Aligned approval action inputs               | Updated manual approval steps to use supported parameters and instructions via `issue-body`. | ~2 min     |
| 2025-10-20 19:38  | Granted issue access for approvals           | Added `issues: write` permission to demo job so manual approval action can open tracking issues. | ~1 min     |
| 2025-10-20 19:46  | Relaxed DynamoDB scope for state locking     | Wildcarded DynamoDB ARN, added `iam:TagRole`, and documented the updates so Terraform can manage locks and role tags. | ~3 min     |
| 2025-10-20 19:52  | Switched demo approvals to environments      | Replaced issue-based approvals with environment-gated apply/destroy jobs in `terraform-validate` workflow. | ~4 min     |
| 2025-10-20 19:58  | Granted Terraform role policy inspection     | Added `iam:ListRolePolicies` permission and documented the requirement for flow log role updates. | ~2 min     |

Add new rows as work progresses, noting the command references or pull requests where relevant.
