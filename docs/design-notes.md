Here’s a Git flow that keeps things simple, reproducible, and safe for Terraform:

  ———

  ### Branch Strategy

  1. main = production truth.
      - No direct pushes; protect the branch so only PRs from `development` can merge.
      - Require at least one approval from the repository owner (me) before merging.
  2. development = integration branch.
      - Day-to-day work lands here via direct pushes (small fixes) or PRs from feature branches.
      - Keep it deployable so promoting to `main` is a fast forward + review cycle.
  3. Short-lived feature branches.
      - Create `feature/<ticket>` branches off `development`.
      - Push regularly, open PRs targeting `development`, and squash when they merge.
  4. One PR = one change.
      - Keeps reviews small and makes it easy to cherry-pick into `main` when needed.
      - Rebase (or fast-forward) before merging to avoid merge commits.

  ———

  ### CI / Demo

  - The `Prepare for Demo` workflow runs on every PR/push, enforcing fmt/tflint/tfsec/init/plan and uploading the plan artifact for review.
  - When triggered manually (`workflow_dispatch`), that same workflow exposes `Demo (apply)`/`Demo (destroy)` jobs. Approve the `demo-*`/`teardown-*`
    environments to run init → plan → apply → verify → optional destroy.

  ———

  ### Promotion & Releases

  - Once the PR is merged, promotion to production is “terraform apply” from main. Use tags or release branches only if you need to maintain multiple versions.
    Otherwise, trunk-based works well: each merge to main is deployable.
  - Keep environment-specific state/backends (backend-test.hcl, backend-prod.hcl). Avoid manually switching them on a feature branch—use the helper script or the
    workflows to stay consistent.
  - Production runs span three Availability Zones (`az_count = 3` in `environments/prod/vars.tfvars`). Validate any module changes against that topology before release.
  - Test and prod now use different CIDR ranges (`10.0.0.0/16` vs `10.1.0.0/16`). Keep them unique to avoid future VPC peering or routing conflicts.

  ———

  ### Policy Reuse

  All IAM/S3/KMS policy JSON lives under infra/policies/.

  - During initial setup or when policies change:

    ./infra/scripts/bootstrap.sh --profile terraform-role --env test
    (Add --skip-iam for pure Terraform runs; --apply to run apply automatically.)

  ———

  ### Best Practices

  - Require at least one reviewer (preferably someone familiar with the infrastructure).
  - Keep commits atomic and descriptive; squash-merge PRs if you prefer a clean history.
  - Handle hotfixes off main in the same short-lived-branch manner—don’t commit directly.
  - Document manual steps in docs/local-development.md so the process stays repeatable.
  - Use the verify_nat.sh script (and soon the Lambdas) to capture proof the deployment works during demos.

  Following this flow, every change is reviewed, validated by CI, demoed when needed, and merged into a single source of truth before production apply.

  ---

### NAT instance management (2025-10-26 refresh)

  - Each Availability Zone now owns a single-instance Auto Scaling Group backed by the hardened NAT launch template.
  - Static Elastic IPs remain allocated per AZ, but a lightweight Lambda (`nat-asg-hook`) attaches them to whichever instance the ASG launches and rewires the private route tables to the new ENI.
  - The hook fires via EventBridge (“EC2 Instance Launch Successful”) so replacements triggered by health checks or manual instance refreshes automatically restore routing without additional tooling.
  - Terraform continues to manage every component—ASGs, launch templates, Lambda, IAM, and EventBridge—keeping destroys/applys deterministic. NAT ASGs now depend explicitly on the hook/EventBridge resources so the first post-apply launch can’t race the automation.
