# Deploy and Destroy Workflow

## Overview

The `deploy-and-destroy.yml` workflow is designed to **automatically deploy infrastructure, optionally run a demo, and always destroy resources at the end** to minimize AWS costs. This is ideal for:

- Testing infrastructure changes
- Demonstrating the NAT gateway alternative
- Validating deployments without leaving resources running
- Cost-effective infrastructure validation

## Workflow Behavior

1. **Deploy Job**: Creates all infrastructure resources
2. **Demo Job** (optional): Runs verification and collects logs (can be skipped)
3. **Destroy Job**: Always runs at the end to clean up resources, even if previous jobs fail

## Triggering the Workflow

### Via GitHub UI

1. Go to **Actions** tab in your repository
2. Select **"Deploy and Destroy Infrastructure"** workflow
3. Click **"Run workflow"**
4. Choose:
   - **Environment**: `test` or `prod`
   - **Run demo**: `true` to run verification, `false` to skip
5. Click **"Run workflow"**

### Via GitHub CLI

```bash
gh workflow run "Deploy and Destroy Infrastructure" \
  --field environment=test \
  --field run_demo=false
```

Or with demo enabled:

```bash
gh workflow run "Deploy and Destroy Infrastructure" \
  --field environment=test \
  --field run_demo=true
```

## Workflow Jobs

### 1. Deploy Job

**Purpose**: Deploy all infrastructure resources

**Steps**:
- Checkout code
- Set up Terraform
- Configure AWS credentials (OIDC)
- Initialize Terraform with environment-specific backend
- Plan infrastructure changes
- Apply infrastructure

**Timeout**: 30 minutes

**Output**: Infrastructure is deployed and ready

### 2. Demo Job (Optional)

**Purpose**: Verify deployment and collect logs

**Condition**: Only runs if `run_demo=true`

**Steps**:
- Run `verify_nat.sh` script to check NAT instances
- Collect probe logs via SSM

**Timeout**: 15 minutes

**Output**: Verification results and logs

### 3. Destroy Job

**Purpose**: Always destroy resources to save costs

**Condition**: Always runs after deploy (and demo if enabled), even if previous jobs fail

**Steps**:
- Checkout code
- Set up Terraform
- Configure AWS credentials
- Initialize Terraform
- Destroy all resources
- Verify destruction

**Timeout**: 20 minutes

**Output**: All resources destroyed

## Key Features

### Automatic Cleanup

The destroy job uses `if: always()` condition, which means it will run:
- ✅ After successful deployment
- ✅ After failed deployment (to clean up partial resources)
- ✅ After demo (if enabled)
- ✅ Even if demo fails

This ensures resources are **always** cleaned up, preventing unexpected AWS costs.

### Timeouts

Each job has a timeout to prevent hanging workflows:
- Deploy: 30 minutes
- Demo: 15 minutes
- Destroy: 20 minutes

### Error Handling

- Destroy job uses `continue-on-error: true` to ensure it completes even if there are issues
- Verification steps in destroy job are non-blocking

## Example Workflow Run

### Scenario 1: Quick Deploy and Destroy (No Demo)

```bash
gh workflow run "Deploy and Destroy Infrastructure" \
  --field environment=test \
  --field run_demo=false
```

**Timeline**:
1. Deploy job runs (~5-10 minutes)
2. Demo job is skipped
3. Destroy job runs (~3-5 minutes)
4. **Total**: ~8-15 minutes

### Scenario 2: Deploy, Demo, and Destroy

```bash
gh workflow run "Deploy and Destroy Infrastructure" \
  --field environment=test \
  --field run_demo=true
```

**Timeline**:
1. Deploy job runs (~5-10 minutes)
2. Demo job runs (~2-5 minutes)
3. Destroy job runs (~3-5 minutes)
4. **Total**: ~10-20 minutes

## Cost Considerations

### Typical Costs Per Run

- **EC2 Instances**:
  - NAT instances (t3.small): ~$0.02/hour × 2-3 instances × ~0.2 hours = ~$0.01-0.02
  - Probe instances (t3.nano): ~$0.005/hour × 2-3 instances × ~0.2 hours = ~$0.002-0.003
- **Data Transfer**: Minimal (outbound only, small amounts)
- **Lambda**: Free tier covers most invocations
- **CloudWatch Logs**: ~$0.50/GB ingested, minimal for short runs

**Estimated cost per workflow run**: **$0.01 - $0.05**

### Cost Savings

By automatically destroying resources:
- ✅ No idle resources left running
- ✅ No forgotten test environments
- ✅ Predictable costs per run
- ✅ No manual cleanup required

## Troubleshooting

### Destroy Job Fails

If the destroy job fails, check:

1. **Terraform state locked**: Another process might be using the state
   - Solution: Wait a few minutes and re-run, or manually unlock if needed

2. **Resources already destroyed**: Some resources might have been manually deleted
   - Solution: The workflow will continue and report what's left

3. **AWS permissions**: The role might not have destroy permissions
   - Solution: Check IAM role policies

### Demo Job Fails

If demo fails, the destroy job will still run. Check:

1. **NAT instances not ready**: Wait time might be too short
   - Solution: Increase timeout or add retry logic

2. **SSM agent not ready**: Probe instances might not have SSM agent running
   - Solution: Check instance IAM role has SSM permissions

### Workflow Times Out

If a job times out:

1. **Deploy timeout**: Infrastructure might be taking longer than expected
   - Solution: Increase timeout in workflow file

2. **Destroy timeout**: Large infrastructure might take longer to destroy
   - Solution: Increase destroy timeout, or destroy in stages

## Comparison with Other Workflows

| Feature | `deploy-and-destroy.yml` | `prepare-for-demo.yml` |
|---------|-------------------------|------------------------|
| **Purpose** | Quick deploy/destroy cycle | Validation + optional demo |
| **Auto-destroy** | ✅ Always | ⚠️ Optional (requires input) |
| **Environment approvals** | ❌ None | ✅ Required for demo/teardown |
| **Use case** | Testing, validation | Production-like demos |
| **Cost control** | ✅ Automatic | ⚠️ Manual approval needed |

## Best Practices

1. **Use for testing**: Perfect for validating infrastructure changes
2. **Skip demo for speed**: Set `run_demo=false` for faster cycles
3. **Monitor costs**: Check AWS Cost Explorer after runs
4. **Review logs**: Check workflow logs if destroy fails
5. **Use test environment**: Prefer `test` environment for frequent runs

## Required Setup

### GitHub Variables

Ensure these are set in repository settings:

```bash
gh variable set AWS_ROLE_TO_ASSUME --body "arn:aws:iam::197496953931:role/github-actions-cdk"
gh variable set AWS_REGION --body "eu-central-1"
gh secret set AWS_ACCOUNT_ID --body "197496953931"
```

### AWS IAM Role

The workflow requires an IAM role with:
- OIDC trust relationship for GitHub Actions
- Permissions to create/destroy infrastructure
- See `docs/github-actions-pipeline.md` for setup details

### Terraform Backend

Ensure backend configuration files exist:
- `infra/backend-test.hcl`
- `infra/backend-prod.hcl`

## Next Steps

- ✅ Workflow is ready to use
- 🔄 Consider adding notifications (Slack, email) on completion
- 🔄 Consider adding cost tracking/reporting
- 🔄 Consider adding scheduled runs for validation
