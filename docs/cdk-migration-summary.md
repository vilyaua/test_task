# CDK Migration Quick Reference

## Overview

This is a quick reference guide for migrating from Terraform to AWS CDK (Python). See `cdk-migration-plan.md` for the complete detailed plan.

## Key Mappings

### Resource Mappings

| Terraform | CDK (Python) | Module |
|----------|--------------|--------|
| `aws_vpc` | `ec2.Vpc` | `aws-cdk-lib` |
| `aws_subnet` | `ec2.Subnet` | `aws-cdk-lib` |
| `aws_autoscaling_group` | `autoscaling.AutoScalingGroup` | `aws-cdk-lib` |
| `aws_launch_template` | `autoscaling.LaunchTemplate` | `aws-cdk-lib` |
| `aws_lambda_function` | `lambda.Function` | `aws-cdk-lib` |
| `aws_iam_role` | `iam.Role` | `aws-cdk-lib` |
| `aws_cloudwatch_log_group` | `logs.LogGroup` | `aws-cdk-lib` |
| `aws_eip` | `ec2.CfnEIP` | `aws-cdk-lib` (L1) |

### File Structure

```
Terraform Structure          →  CDK Structure
─────────────────────────────────────────────────
infra/network.tf             →  cdk/infra/network_stack.py
infra/nat_instances.tf       →  cdk/infra/nat_instances_stack.py
infra/iam.tf                 →  cdk/infra/iam_stack.py
infra/lambda/*.tf            →  cdk/infra/lambda_stack.py
infra/logging.tf             →  cdk/infra/logging_stack.py
infra/variables.tf           →  cdk/config/{env}_config.py
infra/environments/*/        →  cdk/config/{env}_config.py
```

## Quick Start Commands

### Setup
```bash
# Install CDK CLI
npm install -g aws-cdk

# Install Python dependencies (using uv or pip)
# Option 1: With virtual environment (recommended)
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Option 2: System-wide
uv pip install --system -r requirements.txt

# Or using pip:
pip install -r requirements.txt

# Bootstrap CDK (one-time per account/region)
cdk bootstrap aws://197496953931/eu-central-1
```

### Development
```bash
# Synthesize CloudFormation template
cdk synth

# Show differences
cdk diff

# Deploy
cdk deploy NatAlternativeTest

# Destroy
cdk destroy NatAlternativeTest
```

## Configuration Example

### Terraform (vars.tfvars)
```hcl
environment = "test"
project = "nat-alternative"
az_count = 2
vpc_cidr = "10.0.0.0/16"
```

### CDK (config/test_config.py)
```python
@dataclass
class TestConfig:
    environment: str = "test"
    project: str = "nat-alternative"
    az_count: int = 2
    vpc_cidr: str = "10.0.0.16"
```

## Common Patterns

### VPC Creation
```python
# Terraform
resource "aws_vpc" "this" {
  cidr_block = var.vpc_cidr
}

# CDK
vpc = ec2.Vpc(
    self, "NATVpc",
    ip_addresses=ec2.IpAddresses.cidr(props.vpc_cidr),
    max_azs=props.az_count
)
```

### Security Group
```python
# Terraform
resource "aws_security_group" "nat" {
  ingress {
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = [var.vpc_cidr]
  }
}

# CDK
nat_sg = ec2.SecurityGroup(
    self, "NATSG",
    vpc=vpc,
    allow_all_outbound=True
)
nat_sg.add_ingress_rule(
    ec2.Peer.ipv4(props.vpc_cidr),
    ec2.Port.all_traffic()
)
```

### Lambda Function
```python
# Terraform
resource "aws_lambda_function" "hook" {
  filename = "lambda.zip"
  handler = "main.handler"
  runtime = "python3.12"
}

# CDK
hook_lambda = lambda.Function(
    self, "NATASGHook",
    runtime=lambda.Runtime.PYTHON_3_12,
    handler="main.handler",
    code=lambda.Code.from_asset("lambda/nat_asg_hook")
)
```

## Migration Checklist

- [ ] Review `cdk-migration-plan.md`
- [ ] Set up CDK development environment
- [ ] Create CDK project structure
- [ ] Port networking resources
- [ ] Port NAT instances
- [ ] Port IAM roles
- [ ] Port Lambda functions
- [ ] Port logging resources
- [ ] Port test probes
- [ ] Integrate all stacks
- [ ] Update CI/CD pipeline
- [ ] Deploy to test environment
- [ ] Validate functionality
- [ ] Deploy to production
- [ ] Archive Terraform code

## Timeline

**Estimated Duration:** 4-6 weeks

- Week 1-2: Core infrastructure (VPC, NAT, IAM)
- Week 3: Lambda, logging, probes
- Week 4: Integration and testing
- Week 5: Production migration
- Week 6: Cleanup and documentation

## Resources

- [Full Migration Plan](./cdk-migration-plan.md)
- [AWS CDK Python Docs](https://docs.aws.amazon.com/cdk/api/v2/python/)
- [CDK Patterns](https://github.com/cdk-patterns/serverless)
