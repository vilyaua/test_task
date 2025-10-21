Here’s a Git flow that keeps things simple, reproducible, and safe for Terraform:

  ———

  ### Branch Strategy

  1. main = production truth.
      - Always deploy production from main.
      - Protect the branch (required reviews, CI pass, no direct pushes).
  2. Short-lived feature branches.
      - Create feature/<ticket> branches off main.
      - Work locally, commit often, push to GitHub.
      - Open a PR back to main.
  3. One PR = one change.
      - They stay focused and easy to review.
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