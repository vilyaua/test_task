# Terraform vs AWS CDK Comparison

This document provides a side-by-side comparison of Terraform and AWS CDK (Python) approaches for the NAT Gateway Alternative project.

## Overview

| Aspect | Terraform | AWS CDK (Python) |
|--------|-----------|------------------|
| **Language** | HCL (HashiCorp Configuration Language) | Python (or TypeScript, Java, C#, Go) |
| **State Management** | S3 backend + DynamoDB locks | CloudFormation (no separate state file) |
| **Template Format** | `.tf` files | Python code that synthesizes CloudFormation |
| **Provider** | `hashicorp/aws` provider | `aws-cdk-lib` (AWS Construct Library) |
| **Deployment** | `terraform apply` | `cdk deploy` (generates CloudFormation) |
| **Validation** | `terraform validate`, `terraform plan` | `cdk synth`, `cdk diff` |
| **Linting** | `tflint`, `tfsec` | `pylint`, `mypy`, `bandit` |
| **Formatting** | `terraform fmt` | `black`, `isort` |

## Code Examples

### 1. VPC Creation

#### Terraform
```hcl
# network.tf
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-vpc"
  })
}
```

#### CDK (Python)
```python
# network_stack.py
from aws_cdk import (
    aws_ec2 as ec2,
    Tags
)

vpc = ec2.Vpc(
    self, "NATVpc",
    ip_addresses=ec2.IpAddresses.cidr(props.vpc_cidr),
    enable_dns_hostnames=True,
    enable_dns_support=True,
    max_azs=props.az_count
)

Tags.of(vpc).add("Name", f"{props.prefix}-vpc")
Tags.of(vpc).add("Project", props.project)
Tags.of(vpc).add("Environment", props.environment)
```

### 2. Subnet Creation

#### Terraform
```hcl
# network.tf
locals {
  public_subnet_cidrs = {
    for az, idx in local.az_index_map : az => cidrsubnet(var.vpc_cidr, 4, idx)
  }
}

resource "aws_subnet" "public" {
  for_each = local.public_subnet_cidrs

  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value
  availability_zone       = each.key
  map_public_ip_on_launch = true

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-public-${each.key}"
  })
}
```

#### CDK (Python)
```python
# network_stack.py
import ipaddress

def calculate_subnet_cidr(vpc_cidr: str, subnet_index: int, newbits: int = 4) -> str:
    network = ipaddress.ip_network(vpc_cidr, strict=False)
    subnet = list(network.subnets(new_prefix=network.prefixlen + newbits))[subnet_index]
    return str(subnet)

# CDK automatically creates subnets, but for explicit control:
public_subnets = {}
for idx, az in enumerate(vpc.availability_zones):
    subnet = ec2.PublicSubnet(
        self, f"PublicSubnet-{az}",
        vpc=vpc,
        availability_zone=az,
        cidr_block=calculate_subnet_cidr(props.vpc_cidr, idx),
        map_public_ip_on_launch=True
    )
    public_subnets[az] = subnet
```

### 3. Security Group

#### Terraform
```hcl
# nat_instances.tf
resource "aws_security_group" "nat" {
  name        = "${local.prefix}-nat-sg"
  description = "Controls access to NAT instances"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "Allow traffic from private subnets"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = values(local.private_subnet_cidrs)
  }

  egress {
    description = "Allow outbound internet access"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-nat-sg"
  })
}
```

#### CDK (Python)
```python
# nat_instances_stack.py
nat_sg = ec2.SecurityGroup(
    self, "NATSecurityGroup",
    vpc=vpc,
    description="Controls access to NAT instances",
    allow_all_outbound=True
)

# Add ingress from private subnets
for cidr in private_subnet_cidrs.values():
    nat_sg.add_ingress_rule(
        ec2.Peer.ipv4(cidr),
        ec2.Port.all_traffic(),
        "Allow traffic from private subnets"
    )

Tags.of(nat_sg).add("Name", f"{props.prefix}-nat-sg")
```

### 4. Auto Scaling Group

#### Terraform
```hcl
# nat_instances.tf
resource "aws_autoscaling_group" "nat" {
  for_each = local.public_subnet_cidrs

  name                = "${local.prefix}-nat-${replace(each.key, "-", "")}"
  max_size            = 1
  min_size            = 1
  desired_capacity    = 1
  health_check_type   = "EC2"
  vpc_zone_identifier = [aws_subnet.public[each.key].id]

  launch_template {
    id      = aws_launch_template.nat[each.key].id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "${local.prefix}-nat-${each.key}"
    propagate_at_launch = true
  }
}
```

#### CDK (Python)
```python
# nat_instances_stack.py
for az, subnet in public_subnets.items():
    asg = autoscaling.AutoScalingGroup(
        self, f"NATASG-{az}",
        vpc=vpc,
        vpc_subnets=ec2.SubnetSelection(subnets=[subnet]),
        launch_template=launch_template,
        min_capacity=1,
        max_capacity=1,
        desired_capacity=1,
        health_check=autoscaling.HealthCheck.ec2()
    )
    
    Tags.of(asg).add("Name", f"{props.prefix}-nat-{az}")
```

### 5. Lambda Function

#### Terraform
```hcl
# nat_asg_automation.tf
data "archive_file" "nat_asg_hook" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/nat_asg_hook"
  output_path = "${path.module}/lambda/nat_asg_hook.zip"
}

resource "aws_lambda_function" "nat_asg_hook" {
  function_name = "${local.prefix}-nat-asg-hook"
  role          = aws_iam_role.nat_asg_hook.arn
  handler       = "main.handler"
  runtime       = "python3.12"

  filename         = data.archive_file.nat_asg_hook.output_path
  source_code_hash = data.archive_file.nat_asg_hook.output_base64sha256

  environment {
    variables = {
      ROUTE_TABLE_MAP = jsonencode(local.nat_route_table_map)
      EIP_MAP         = jsonencode({ for az, eip in aws_eip.nat : az => eip.allocation_id })
    }
  }

  timeout = 60
}
```

#### CDK (Python)
```python
# lambda_stack.py
nat_hook_lambda = lambda.Function(
    self, "NATASGHook",
    function_name=f"{props.prefix}-nat-asg-hook",
    runtime=lambda.Runtime.PYTHON_3_12,
    handler="main.handler",
    code=lambda.Code.from_asset("lambda/nat_asg_hook"),
    role=nat_hook_role,
    timeout=Duration.minutes(1),
    environment={
        "ROUTE_TABLE_MAP": json.dumps(route_table_map),
        "EIP_MAP": json.dumps(eip_map)
    }
)
```

### 6. EventBridge Rule

#### Terraform
```hcl
# nat_asg_automation.tf
resource "aws_cloudwatch_event_rule" "nat_asg_hook" {
  name        = "${local.prefix}-nat-asg-launch"
  description = "Invoke Lambda when NAT ASG instances launch successfully."

  event_pattern = jsonencode({
    "source" : ["aws.autoscaling"],
    "detail-type" : ["EC2 Instance Launch Successful"],
    "detail" : {
      "AutoScalingGroupName" : local.nat_asg_names
    }
  })
}

resource "aws_cloudwatch_event_target" "nat_asg_hook" {
  rule      = aws_cloudwatch_event_rule.nat_asg_hook.name
  target_id = "nat-asg-hook"
  arn       = aws_lambda_function.nat_asg_hook.arn
}
```

#### CDK (Python)
```python
# lambda_stack.py
rule = events.Rule(
    self, "NATASGLaunchRule",
    description="Invoke Lambda when NAT ASG instances launch successfully",
    event_pattern=events.EventPattern(
        source=["aws.autoscaling"],
        detail_type=["EC2 Instance Launch Successful"],
        detail={
            "AutoScalingGroupName": nat_asg_names
        }
    )
)

rule.add_target(targets.LambdaFunction(nat_hook_lambda))
```

### 7. IAM Role

#### Terraform
```hcl
# iam.tf
resource "aws_iam_role" "instance" {
  name = "${local.prefix}-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "instance_ssm_core" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
```

#### CDK (Python)
```python
# iam_stack.py
nat_role = iam.Role(
    self, "NATInstanceRole",
    role_name=f"{props.prefix}-instance-role",
    assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
    managed_policies=[
        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
        iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy")
    ]
)
```

### 8. CloudWatch Log Group

#### Terraform
```hcl
# logging.tf
resource "aws_cloudwatch_log_group" "nat_instances" {
  name              = "/nat/${local.prefix}/nat"
  retention_in_days = var.app_log_retention_days
  kms_key_id        = local.app_logs_kms_arn

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-nat-logs"
  })
}
```

#### CDK (Python)
```python
# logging_stack.py
nat_log_group = logs.LogGroup(
    self, "NATInstancesLogs",
    log_group_name=f"/nat/{props.prefix}/nat",
    retention=logs.RetentionDays.TWO_WEEKS,
    encryption_key=kms_key
)

Tags.of(nat_log_group).add("Name", f"{props.prefix}-nat-logs")
```

## Key Differences

### 1. State Management

**Terraform:**
- Requires S3 backend for state storage
- Uses DynamoDB for state locking
- State file contains resource mappings
- Manual state import/export for migration

**CDK:**
- No separate state file
- CloudFormation manages state
- State is implicit in CloudFormation stack
- Easier to recreate (no state import needed)

### 2. Resource Dependencies

**Terraform:**
- Explicit `depends_on` blocks
- Implicit dependencies via resource references
- Can create circular dependencies if not careful

**CDK:**
- Automatic dependency resolution
- Dependencies created when resources reference each other
- Type-safe references prevent many errors

### 3. Loops and Conditionals

**Terraform:**
- `for_each` for resource iteration
- `count` for conditional creation
- `for` expressions for data transformation

**CDK:**
- Python `for` loops for iteration
- Python `if` statements for conditionals
- Full Python language features available

### 4. Variable Management

**Terraform:**
- `variables.tf` with type definitions
- `vars.tfvars` files for values
- `terraform.tfvars` for defaults

**CDK:**
- Python dataclasses or classes for configuration
- Environment-specific config files
- Type hints for validation

### 5. Outputs

**Terraform:**
```hcl
output "vpc_id" {
  value = aws_vpc.this.id
}
```

**CDK:**
```python
CfnOutput(self, "VpcId", value=vpc.vpc_id)
```

### 6. Data Sources

**Terraform:**
```hcl
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}
```

**CDK:**
```python
# Use SSM Parameter Store
ami = ec2.MachineImage.latest_amazon_linux2023()
# Or explicit SSM lookup
ami_id = ssm.StringParameter.value_from_lookup(
    self, "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
)
```

## CI/CD Comparison

### Terraform Workflow
```yaml
- name: Terraform Format
  run: terraform fmt -check

- name: Terraform Lint
  run: tflint infra/

- name: Terraform Security
  run: tfsec infra/

- name: Terraform Validate
  run: terraform validate infra/

- name: Terraform Plan
  run: terraform plan -var-file=environments/test/vars.tfvars
```

### CDK Workflow
```yaml
- name: Python Format Check
  run: black --check cdk/

- name: Python Lint
  run: pylint cdk/

- name: Type Check
  run: mypy cdk/

- name: CDK Synthesize
  run: cdk synth

- name: CDK Diff
  run: cdk diff
```

## Pros and Cons

### Terraform Pros
- ✅ Declarative, infrastructure-focused language
- ✅ Multi-cloud support
- ✅ Mature ecosystem
- ✅ Strong state management
- ✅ Plan before apply (safety)

### Terraform Cons
- ❌ Limited programming constructs
- ❌ Separate state management
- ❌ HCL learning curve
- ❌ Less type safety

### CDK Pros
- ✅ Full programming language (Python)
- ✅ Type safety and IDE support
- ✅ Reusable constructs
- ✅ No separate state file
- ✅ Better for complex logic
- ✅ Native AWS integration

### CDK Cons
- ❌ AWS-only (CloudFormation)
- ❌ Larger learning curve for non-programmers
- ❌ CloudFormation stack limits
- ❌ Less mature than Terraform

## Migration Decision Factors

Choose **CDK** if:
- Team is comfortable with Python
- Want type safety and IDE support
- Need complex logic in infrastructure code
- AWS-only infrastructure
- Prefer CloudFormation-native approach

Choose **Terraform** if:
- Multi-cloud requirements
- Team prefers declarative IaC
- Existing Terraform expertise
- Need Terraform-specific features (workspaces, etc.)

## Recommendation

For this project, **CDK (Python)** is recommended because:
1. The infrastructure is AWS-only
2. Python Lambda functions already exist
3. Type safety helps prevent errors
4. Better integration with existing Python tooling
5. CloudFormation state management is simpler
6. Reusable constructs for future projects

