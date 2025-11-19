# Local Development Checklist

Use this checklist to validate changes before opening a pull request or pushing to `main`.

## 1. Prerequisites
- Install AWS CDK CLI: `npm install -g aws-cdk`
- Install Python 3.12+ and package manager (`pip` or `uv`)
- Install Python dependencies:
  - Using `uv` (recommended): `uv pip install -r requirements.txt`
  - Using `pip`: `pip install -r requirements.txt`
- Configure AWS credentials via `~/.aws/credentials` or environment variables
- Ensure you have permissions to create VPC, EC2, Lambda, IAM, CloudFormation resources

## 2. Formatting & Linting

### Using Pre-commit (Recommended)

Pre-commit hooks automatically format and validate code before commits:

```bash
# Install pre-commit hooks (one-time setup)
pre-commit install

# Run hooks manually on all files
pre-commit run --all-files
```

**Skip hooks if needed:** `git commit --no-verify -m "message"` (use sparingly, then run `pre-commit run --all-files` afterward)

See `docs/pre-commit-setup.md` for detailed setup instructions.

### Manual Formatting & Linting

Run from the repository root:

```bash
# Format Python code
black cdk/
isort cdk/

# Type checking
mypy cdk/

# Linting
pylint cdk/
```

Fix warnings before committing.

## 3. CDK Validation
```bash
# Synthesize CloudFormation template
cdk synth --context environment=test

# Show differences (if stack exists)
cdk diff --context environment=test

# Validate CloudFormation template
cdk synth --context environment=test > template.json
aws cloudformation validate-template --template-body file://template.json
```

Review the synthesized template and ensure only intended changes are present.

## 4. Deploy Locally (Optional)
```bash
# Bootstrap CDK (one-time per account/region)
cdk bootstrap aws://197496953931/eu-central-1

# Deploy to test environment
cdk deploy --context environment=test

# Deploy to production environment
cdk deploy --context environment=prod
```

## 5. Verify Deployment
After deploying, verify NAT connectivity:
```bash
cd infra
./scripts/verify_nat.sh test
```

## 6. Configuration
- Environment configurations live in `cdk/config/test_config.py` and `cdk/config/prod_config.py`
- Stack name is determined by environment: `NatAlternativeTest` or `NatAlternativeProd`
- Context can be passed via `--context environment=test` or environment variable `CDK_ENVIRONMENT`

## 7. GitHub Actions Parity
The `.github/workflows/deploy-and-destroy.yml` workflow mirrors these steps:
- Installs Python dependencies
- Runs `cdk synth` to validate
- Deploys with `cdk deploy`
- Optionally runs verification
- Always destroys resources at the end

Green results locally usually indicate the workflows will pass.

## 8. Destroy Resources
```bash
# Destroy test environment
cdk destroy --context environment=test

# Destroy production environment
cdk destroy --context environment=prod
```

**Note:** Always destroy resources after testing to avoid unexpected costs.
