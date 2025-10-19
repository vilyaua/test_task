# Repository Guidelines

This project defines a resilient AWS-based NAT gateway alternative. Use these guidelines to keep documentation, infrastructure code, and automation aligned.

## Project Structure & Module Organization
- `README.md` captures the problem statement; refresh it when architecture, workflows, or dependencies change.
- `docs/` holds diagrams (`architecture-diagram.mmd`, exported PNG) and design notes; commit regenerated assets with the Markdown.
- `infra/` (Terraform root) contains modules plus per-environment stacks; keep Lambda sources in `infra/lambda/` and automation in `infra/scripts/`.
- `.github/workflows/` runs CI/CD; follow the existing `test`, `deploy-test`, and `deploy-prod` separation.
- `environments/<env>/` stores backend and variable files; keep folder names short (`test`, `prod`).

## Build, Test, and Development Commands
- `terraform fmt infra/` — normalize Terraform style before committing.
- `tflint infra/` and `tfsec infra/` — static analysis for Terraform.
- `terraform validate infra/` — schema validation shared with CI.
- `terraform plan -var-file=environments/test/vars.tfvars` — verify desired changes; swap var-files per target environment.
- `python -m pytest infra/lambda` — exercise Lambda helpers when Python code exists.

## Coding Style & Naming Conventions
- Terraform files must remain `terraform fmt` clean with two-space indentation; module names use hyphenated, functional nouns (e.g., `nat-instance`, `route-failover`).
- Shell scripts in `infra/scripts/` start with `#!/usr/bin/env bash`, enable `set -euo pipefail`, and keep function names lower_snake_case.
- Python utilities adopt `black`, `isort`, and `mypy`-friendly typing; package paths stay lower_snake_case.
- Resource names in IaC follow `nat-<component>-<az|env>` to match the diagrams.

## Testing Guidelines
- Use `terraform plan -detailed-exitcode` in sandbox accounts and attach outputs to PRs.
- Require green runs of `tflint`, `tfsec`, `terraform validate`, and relevant `pytest` suites before review.
- New Lambda logic includes idempotent smoke tests (e.g., `nat-health-probe`) and updates CloudWatch alarms alongside code.

## Commit & Pull Request Guidelines
- Follow the existing Git history: concise, imperative subjects (`Add NAT gateway alternative architecture docs`, `Update README.md`); wrap bodies at 72 characters.
- Reference tickets or RFCs in the body, list manual testing, and note which environments were planned or applied.
- Pull requests describe architecture impacts, attach refreshed diagrams from `docs/`, and link to successful Terraform plans.
- Request at least one reviewer with AWS networking context and call out post-merge operational tasks.
