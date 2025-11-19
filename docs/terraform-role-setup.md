# ⚠️ Legacy Documentation: Terraform Role Setup

**This document is archived and no longer applicable.** The project has migrated from Terraform to AWS CDK (Python).

For current setup instructions, see:
- `infra/policies/README.md` - IAM policies and roles for CDK deployment
- `docs/local-development.md` - Local development with CDK
- `docs/github-actions-pipeline.md` - GitHub Actions workflow setup

---

## Historical Context

This document previously described:
- Terraform IAM user and role setup
- S3 backend and DynamoDB state locking
- Terraform-specific IAM policies

These are no longer needed as CDK uses CloudFormation for state management and OIDC for authentication.
