# Repository Guidelines

This project defines a resilient AWS-based NAT gateway alternative. Use these guidelines to keep documentation, infrastructure code, and automation aligned.

## Project Structure & Module Organization
- `README.md` captures the problem statement; refresh it when workflows or dependencies change.
- `docs/` holds design notes (`docs/design-notes.md` — e.g., `/Users/vper/!coding/HR_Tasks/RavenPack/test_task/docs/design-notes.md` locally) and other documentation.
- `cdk/` contains CDK stack definitions and environment configurations; keep Lambda sources in `infra/lambda/` and automation in `infra/scripts/`.
- `.github/workflows/` runs CI/CD; follow the existing deploy-and-destroy workflow pattern.
- `cdk/config/` stores environment-specific configuration files (`test_config.py`, `prod_config.py`).

## Build, Test, and Development Commands
- `black cdk/` and `isort cdk/` — normalize Python code style before committing.
- `mypy cdk/` and `pylint cdk/` — static analysis for Python/CDK code.
- `cdk synth --context environment=test` — synthesize CloudFormation template for validation.
- `cdk diff --context environment=test` — show differences from deployed stack.
- `cdk deploy --context environment=test` — deploy infrastructure to test environment.
- `python -m pytest infra/lambda` — exercise Lambda helpers when Python code exists.
- Request elevated command approvals before leaving the sandbox (e.g., provider downloads, AWS CLI calls); use the CLI’s escalation prompt with a one-sentence justification.

## Coding Style & Naming Conventions
- CDK Python code must follow `black` and `isort` formatting; use type hints and `mypy`-compatible typing.
- Shell scripts in `infra/scripts/` start with `#!/usr/bin/env bash`, enable `set -euo pipefail`, and keep function names lower_snake_case.
- Python utilities adopt `black`, `isort`, and `mypy`-friendly typing; package paths stay lower_snake_case.
- Resource names in CDK follow `nat-<component>-<az|env>` pattern for consistency.

## Testing Guidelines
- Use `cdk synth` and `cdk diff` in sandbox accounts and attach outputs to PRs.
- Require green runs of `black`, `isort`, `mypy`, `pylint`, and relevant `pytest` suites before review.
- New Lambda logic includes idempotent smoke tests (e.g., `nat-health-probe`) and updates CloudWatch alarms alongside code.

## Commit & Pull Request Guidelines
- Follow the existing Git history: concise, imperative subjects (`Add NAT gateway alternative docs`, `Update README.md`); wrap bodies at 72 characters.
- Reference tickets or RFCs in the body, list manual testing, and note which environments were planned or applied.
- Pull requests describe infrastructure changes and link to successful CDK deployments.
- Request at least one reviewer with AWS networking context and call out post-merge operational tasks.
