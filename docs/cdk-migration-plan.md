# AWS CDK (Python) Migration Plan

## Executive Summary

This document outlines the migration strategy for converting the NAT Gateway Alternative infrastructure from Terraform to AWS CDK (Python). The migration will preserve all existing functionality while leveraging CDK's programmatic approach, type safety, and CloudFormation synthesis capabilities.

**Current State:** Terraform-based infrastructure with 12 `.tf` files managing VPC, NAT instances, Lambda functions, IAM roles, logging, and monitoring.

**Target State:** AWS CDK (Python) stack with modular constructs, preserving multi-environment support (test/prod) and all existing automation.

---

## 1. Project Overview

### 1.1 Current Infrastructure Components

| Component | Terraform Files | Resources |
|-----------|----------------|-----------|
| **Networking** | `network.tf` | VPC, Subnets (public/private), Route Tables, Internet Gateway |
| **NAT Instances** | `nat_instances.tf` | Launch Templates, Auto Scaling Groups, Security Groups, Elastic IPs |
| **IAM** | `iam.tf` | Instance Roles, Policies, Instance Profiles |
| **Lambda Functions** | `nat_asg_automation.tf`, `log_collector_lambda.tf` | 3 Lambda functions with EventBridge triggers |
| **Logging & Monitoring** | `logging.tf` | CloudWatch Log Groups, VPC Flow Logs, KMS keys |
| **Test Probes** | `test_probes.tf` | EC2 instances for connectivity validation |
| **Configuration** | `variables.tf`, `outputs.tf`, `main.tf` | Variables, outputs, locals |

### 1.2 Key Features to Preserve

- ✅ Multi-AZ high availability (2 AZs for test, 3 for prod)
- ✅ Auto Scaling Groups with single-instance per AZ
- ✅ Lambda-driven route table automation on instance launch
- ✅ VPC Flow Logs with KMS encryption
- ✅ CloudWatch logging for NAT instances and probes
- ✅ Environment-specific configuration (test/prod)
- ✅ S3 backend for state management (CDK uses CloudFormation)
- ✅ IAM least-privilege policies
- ✅ Security hardening (IMDSv2, encrypted volumes, source/dest check)

---

## 2. Migration Strategy

### 2.1 Approach: Big Bang vs. Incremental

**Recommended: Incremental Migration with Parallel Run**

1. **Phase 1:** Create CDK stack alongside Terraform (no deployment)
2. **Phase 2:** Deploy CDK to a new test environment for validation
3. **Phase 3:** Migrate test environment from Terraform to CDK
4. **Phase 4:** Migrate production environment
5. **Phase 5:** Remove Terraform codebase

**Rationale:** Reduces risk, allows validation, and maintains rollback capability.

### 2.2 State Management

- **Terraform:** S3 backend with DynamoDB locking
- **CDK:** CloudFormation stacks (no separate state file)
- **Migration:** Export Terraform state → Import to CloudFormation (or recreate)

**Note:** CDK synthesizes CloudFormation templates, so state is managed by CloudFormation service.

---

## 3. Component Mapping: Terraform → CDK

### 3.1 Networking (`network.tf` → `cdk/infra/network_stack.py`)

| Terraform Resource | CDK Construct | Notes |
|-------------------|---------------|-------|
| `aws_vpc` | `ec2.Vpc` | Use `max_azs` parameter |
| `aws_subnet` (public) | `ec2.PublicSubnet` | Created via `Vpc.add_public_subnet()` |
| `aws_subnet` (private) | `ec2.PrivateSubnet` | Created via `Vpc.add_private_subnet()` |
| `aws_internet_gateway` | `ec2.InternetGateway` | Auto-created by `Vpc` |
| `aws_route_table` | `ec2.PublicRouteTable` / `ec2.PrivateRouteTable` | Auto-created by subnets |
| `aws_route` | `ec2.Route` | Use `add_route()` method |

**CDK Pattern:**
```python
vpc = ec2.Vpc(
    self, "NATVpc",
    ip_addresses=ec2.IpAddresses.cidr(props.vpc_cidr),
    max_azs=props.az_count,
    nat_gateways=0,  # We use NAT instances
    subnet_configuration=[
        ec2.SubnetConfiguration(
            name="public",
            subnet_type=ec2.SubnetType.PUBLIC,
            cidr_mask=20
        ),
        ec2.SubnetConfiguration(
            name="private",
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            cidr_mask=20
        )
    ]
)
```

### 3.2 NAT Instances (`nat_instances.tf` → `cdk/infra/nat_stack.py`)

| Terraform Resource | CDK Construct | Notes |
|-------------------|---------------|-------|
| `aws_launch_template` | `autoscaling.LaunchTemplate` | User data via `add_user_data()` |
| `aws_autoscaling_group` | `autoscaling.AutoScalingGroup` | Per-AZ ASG with `min_size=1, max_size=1` |
| `aws_security_group` | `ec2.SecurityGroup` | Ingress/egress rules |
| `aws_eip` | `ec2.CfnEIP` | Use L1 construct for EIP |

**CDK Pattern:**
```python
# Per-AZ NAT instance
for az_idx, az in enumerate(vpc.availability_zones):
    nat_sg = ec2.SecurityGroup(...)
    launch_template = autoscaling.LaunchTemplate(...)
    asg = autoscaling.AutoScalingGroup(
        self, f"NATASG-{az}",
        vpc=vpc,
        vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        launch_template=launch_template,
        min_capacity=1,
        max_capacity=1,
        desired_capacity=1
    )
    eip = ec2.CfnEIP(...)
```

### 3.3 IAM (`iam.tf` → `cdk/infra/iam_stack.py`)

| Terraform Resource | CDK Construct | Notes |
|-------------------|---------------|-------|
| `aws_iam_role` | `iam.Role` | Use `assume_role_policy` |
| `aws_iam_instance_profile` | `iam.CfnInstanceProfile` | Or `Role.add_managed_policy()` |
| `aws_iam_role_policy_attachment` | `role.add_managed_policy()` | Managed policies |
| `aws_iam_role_policy` | `iam.Policy` | Inline policies |

**CDK Pattern:**
```python
nat_role = iam.Role(
    self, "NATInstanceRole",
    assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
    managed_policies=[
        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
        iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy")
    ]
)
```

### 3.4 Lambda Functions (`nat_asg_automation.tf`, `log_collector_lambda.tf` → `cdk/infra/lambda_stack.py`)

| Terraform Resource | CDK Construct | Notes |
|-------------------|---------------|-------|
| `aws_lambda_function` | `lambda.Function` | Use `Code.from_asset()` for local code |
| `aws_lambda_permission` | `lambda.Function.add_permission()` | EventBridge invocation |
| `aws_cloudwatch_event_rule` | `events.Rule` | EventBridge rule |
| `aws_cloudwatch_event_target` | `rule.add_target()` | Lambda target |
| `archive_file` | N/A | CDK handles packaging automatically |

**CDK Pattern:**
```python
nat_hook_lambda = lambda.Function(
    self, "NATASGHook",
    runtime=lambda.Runtime.PYTHON_3_12,
    handler="main.handler",
    code=lambda.Code.from_asset("lambda/nat_asg_hook"),
    environment={
        "ROUTE_TABLE_MAP": json.dumps(route_table_map),
        "EIP_MAP": json.dumps(eip_map)
    }
)

rule = events.Rule(
    self, "NATASGLaunchRule",
    event_pattern=events.EventPattern(
        source=["aws.autoscaling"],
        detail_type=["EC2 Instance Launch Successful"]
    )
)
rule.add_target(targets.LambdaFunction(nat_hook_lambda))
```

### 3.5 Logging (`logging.tf` → `cdk/infra/logging_stack.py`)

| Terraform Resource | CDK Construct | Notes |
|-------------------|---------------|-------|
| `aws_kms_key` | `kms.Key` | Encryption keys |
| `aws_cloudwatch_log_group` | `logs.LogGroup` | Retention and encryption |
| `aws_flow_log` | `ec2.FlowLog` | VPC Flow Logs |
| `aws_iam_role` (flow logs) | `iam.Role` | Service role |

**CDK Pattern:**
```python
log_group = logs.LogGroup(
    self, "NATLogs",
    log_group_name=f"/nat/{props.prefix}/nat",
    retention=logs.RetentionDays.TWO_WEEKS,
    encryption_key=kms_key
)

vpc.add_flow_log(
    "VPCFlowLog",
    destination=ec2.FlowLogDestination.to_cloud_watch_logs(log_group),
    traffic_type=ec2.FlowLogTrafficType.ALL
)
```

### 3.6 Test Probes (`test_probes.tf` → `cdk/infra/probe_stack.py`)

| Terraform Resource | CDK Construct | Notes |
|-------------------|---------------|-------|
| `aws_instance` | `ec2.Instance` | Probe instances |
| `aws_security_group` | `ec2.SecurityGroup` | Probe security group |

**CDK Pattern:**
```python
if props.enable_probes:
    for az, subnet in private_subnets.items():
        probe = ec2.Instance(
            self, f"Probe-{az}",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=[subnet]),
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.NANO),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            user_data=ec2.UserData.custom(probe_user_data)
        )
```

---

## 4. Proposed CDK Project Structure

```
.
├── README.md
├── cdk.json                          # CDK configuration
├── requirements.txt                  # Python dependencies
├── pyproject.toml                    # Python project config (optional)
├── cdk/
│   ├── __init__.py
│   ├── app.py                        # CDK app entry point
│   ├── config/
│   │   ├── __init__.py
│   │   ├── test_config.py            # Test environment config
│   │   └── prod_config.py            # Production environment config
│   ├── infra/
│   │   ├── __init__.py
│   │   ├── nat_stack.py              # Main stack (orchestrates all)
│   │   ├── network_stack.py          # VPC, subnets, routing
│   │   ├── nat_instances_stack.py    # NAT ASGs, launch templates
│   │   ├── iam_stack.py              # IAM roles and policies
│   │   ├── lambda_stack.py           # Lambda functions
│   │   ├── logging_stack.py          # CloudWatch, Flow Logs, KMS
│   │   └── probe_stack.py            # Test probe instances
│   └── constructs/
│       ├── __init__.py
│       ├── nat_instance_construct.py # Reusable NAT instance construct
│       └── lambda_construct.py       # Reusable Lambda construct
├── lambda/                           # Lambda source code (unchanged)
│   ├── nat_asg_hook/
│   ├── log_collector/
│   └── demo_health/
├── scripts/                          # Deployment scripts
│   ├── deploy.sh                     # CDK deploy wrapper
│   ├── destroy.sh                    # CDK destroy wrapper
│   └── verify_nat.sh                 # (unchanged)
└── .github/workflows/
    └── cdk-deploy.yml                # Updated CI/CD workflow
```

### 4.1 Stack Organization Options

**Option A: Monolithic Stack** (Simpler, faster to implement)
- Single `NatAlternativeStack` containing all resources
- Pros: Simple, fewer dependencies
- Cons: Less modular, harder to update individual components

**Option B: Nested Stacks** (More modular)
- Main stack with nested stacks per component
- Pros: Modular, easier to update
- Cons: More complex, CloudFormation stack limits

**Option C: Separate Stacks** (Most flexible)
- Independent stacks per component (NetworkStack, NatStack, etc.)
- Pros: Maximum flexibility, independent updates
- Cons: Cross-stack references, more deployment steps

**Recommendation: Option A for initial migration, refactor to Option C if needed.**

---

## 5. Implementation Phases

### Phase 1: Setup & Foundation (Week 1)

**Tasks:**
- [ ] Install CDK CLI and Python dependencies
- [ ] Initialize CDK project structure
- [ ] Create `cdk.json` configuration
- [ ] Set up environment configuration files (`test_config.py`, `prod_config.py`)
- [ ] Create base stack class with common properties
- [ ] Set up CDK context for environment switching

**Deliverables:**
- CDK project scaffold
- Configuration management
- Basic stack structure

### Phase 2: Core Networking (Week 1-2)

**Tasks:**
- [ ] Implement VPC with public/private subnets
- [ ] Create route tables and associations
- [ ] Implement Internet Gateway
- [ ] Add CIDR calculation logic (equivalent to Terraform `cidrsubnet`)
- [ ] Validate subnet allocation matches Terraform output

**Deliverables:**
- `network_stack.py` with VPC resources
- Unit tests for CIDR calculations

### Phase 3: NAT Instances & ASGs (Week 2)

**Tasks:**
- [ ] Implement security groups for NAT instances
- [ ] Create launch templates with user data
- [ ] Implement Auto Scaling Groups (one per AZ)
- [ ] Allocate Elastic IPs per AZ
- [ ] Add IAM roles and instance profiles
- [ ] Implement source/dest check disable logic

**Deliverables:**
- `nat_instances_stack.py`
- NAT instances deployable independently

### Phase 4: Lambda Functions (Week 2-3)

**Tasks:**
- [ ] Port `nat_asg_hook` Lambda to CDK
- [ ] Port `log_collector` Lambda to CDK
- [ ] Port `demo_health` Lambda to CDK
- [ ] Implement EventBridge rules and targets
- [ ] Configure Lambda permissions
- [ ] Set up CloudWatch log groups for Lambdas

**Deliverables:**
- `lambda_stack.py`
- All Lambda functions deployable

### Phase 5: Logging & Monitoring (Week 3)

**Tasks:**
- [ ] Implement KMS keys for log encryption
- [ ] Create CloudWatch log groups
- [ ] Implement VPC Flow Logs
- [ ] Configure log retention policies
- [ ] Set up IAM roles for Flow Logs

**Deliverables:**
- `logging_stack.py`
- Complete logging infrastructure

### Phase 6: Test Probes (Week 3)

**Tasks:**
- [ ] Implement probe security groups
- [ ] Create probe EC2 instances
- [ ] Configure user data for probes
- [ ] Add conditional deployment (based on `enable_probes`)

**Deliverables:**
- `probe_stack.py`
- Test probes deployable

### Phase 7: Integration & Testing (Week 4)

**Tasks:**
- [ ] Integrate all stacks into main stack
- [ ] Add stack outputs (matching Terraform outputs)
- [ ] Deploy to new test environment
- [ ] Run `verify_nat.sh` validation
- [ ] Compare CDK deployment with Terraform deployment
- [ ] Fix any discrepancies

**Deliverables:**
- Complete CDK stack
- Validated deployment

### Phase 8: CI/CD Migration (Week 4)

**Tasks:**
- [ ] Update GitHub Actions workflow for CDK
- [ ] Replace `terraform fmt/validate` with `cdk synth` and `cdk diff`
- [ ] Update deployment scripts
- [ ] Add CDK-specific linting (pylint, mypy)
- [ ] Test CI/CD pipeline

**Deliverables:**
- Updated `.github/workflows/cdk-deploy.yml`
- Automated deployment pipeline

### Phase 9: Production Migration (Week 5)

**Tasks:**
- [ ] Deploy CDK to test environment (replace Terraform)
- [ ] Validate test environment functionality
- [ ] Deploy CDK to production environment
- [ ] Validate production environment
- [ ] Monitor for 1-2 weeks

**Deliverables:**
- Production CDK deployment
- Migration complete

### Phase 10: Cleanup (Week 6)

**Tasks:**
- [ ] Archive Terraform codebase
- [ ] Update documentation
- [ ] Remove Terraform-specific scripts
- [ ] Update README with CDK instructions

**Deliverables:**
- Clean codebase
- Updated documentation

---

## 6. Configuration Management

### 6.1 Environment Configuration

**CDK Context Approach:**
```python
# cdk/config/test_config.py
from dataclasses import dataclass

@dataclass
class TestConfig:
    environment: str = "test"
    project: str = "nat-alternative"
    az_count: int = 2
    vpc_cidr: str = "10.0.0.0/16"
    nat_instance_type: str = "t3.small"
    enable_probes: bool = True
    logs_kms_key_arn: str = ""  # Will be created by CDK if empty
```

**Usage in Stack:**
```python
# cdk/app.py
from cdk.config.test_config import TestConfig

app = cdk.App()
config = TestConfig()  # or load from context
NatAlternativeStack(app, "NatAlternativeTest", config)
```

### 6.2 Variable Mapping

| Terraform Variable | CDK Config Property | Default |
|-------------------|---------------------|---------|
| `environment` | `config.environment` | "test" |
| `project` | `config.project` | "nat-alternative" |
| `vpc_cidr` | `config.vpc_cidr` | "10.0.0.0/16" |
| `az_count` | `config.az_count` | 2 |
| `nat_instance_type` | `config.nat_instance_type` | "t3.small" |
| `enable_probes` | `config.enable_probes` | True |
| `logs_kms_key_arn` | `config.logs_kms_key_arn` | "" |

---

## 7. Key Technical Considerations

### 7.1 CIDR Subnet Calculation

Terraform uses `cidrsubnet()` function. CDK equivalent:

```python
import ipaddress

def calculate_subnet_cidr(vpc_cidr: str, subnet_index: int, newbits: int = 4) -> str:
    """Calculate subnet CIDR equivalent to Terraform cidrsubnet()"""
    network = ipaddress.ip_network(vpc_cidr, strict=False)
    subnet = list(network.subnets(new_prefix=network.prefixlen + newbits))[subnet_index]
    return str(subnet)
```

### 7.2 User Data Handling

Terraform uses `base64encode()` for user data. CDK handles this automatically:

```python
user_data = ec2.UserData.custom(nat_user_data_script)
# CDK automatically base64-encodes
```

### 7.3 Lambda Code Packaging

Terraform uses `archive_file` data source. CDK handles this automatically:

```python
code = lambda.Code.from_asset("lambda/nat_asg_hook")
# CDK automatically zips and uploads
```

### 7.4 Resource Naming

Terraform uses `local.prefix` for naming. CDK equivalent:

```python
prefix = f"{props.project}-{props.environment}"
# Use in resource IDs: f"{prefix}-nat-sg"
```

### 7.5 Tags

Terraform uses `local.base_tags`. CDK equivalent:

```python
tags = {
    "Project": props.project,
    "Environment": props.environment,
    **props.additional_tags
}
# Apply via: cdk.Tags.of(stack).add(key, value)
```

### 7.6 Dependencies

Terraform uses `depends_on`. CDK uses implicit dependencies via references:

```python
# CDK automatically creates dependencies when you reference resources
asg = autoscaling.AutoScalingGroup(...)
lambda_function.add_environment("ASG_NAME", asg.auto_scaling_group_name)
# CDK ensures lambda is created before ASG references it
```

---

## 8. Testing Strategy

### 8.1 Unit Tests

- **CIDR calculation tests:** Verify subnet allocation matches Terraform
- **Configuration tests:** Validate environment configs
- **Construct tests:** Test individual constructs in isolation

**Tools:** `pytest`, `pytest-cdk`

### 8.2 Integration Tests

- **CDK synth tests:** Verify CloudFormation template generation
- **Diff tests:** Compare CDK-generated templates with Terraform plans
- **Deployment tests:** Deploy to sandbox and validate

**Tools:** `cdk synth`, `cdk diff`, `aws cloudformation validate-template`

### 8.3 Validation Tests

- **Functional tests:** Run `verify_nat.sh` against CDK deployment
- **Lambda tests:** Invoke Lambda functions and verify behavior
- **Connectivity tests:** Verify NAT routing works correctly

---

## 9. CI/CD Updates

### 9.1 GitHub Actions Workflow Changes

**Current Terraform Workflow:**
- `terraform fmt`
- `tflint`
- `tfsec`
- `terraform validate`
- `terraform plan`

**New CDK Workflow:**
- `python -m black cdk/` (formatting)
- `python -m pylint cdk/` (linting)
- `python -m mypy cdk/` (type checking)
- `cdk synth` (synthesize CloudFormation)
- `cdk diff` (show changes)
- `cdk deploy --require-approval never` (deploy)

### 9.2 Deployment Scripts

**New `scripts/deploy.sh`:**
```bash
#!/usr/bin/env bash
set -euo pipefail

ENV=${1:-test}
cdk deploy "NatAlternative${ENV^}" --require-approval never
```

---

## 10. Risk Assessment & Mitigation

### 10.1 Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **State loss during migration** | High | Medium | Deploy CDK to new environment first, validate, then migrate |
| **Resource naming differences** | Medium | High | Use consistent naming patterns, document mappings |
| **Lambda code packaging issues** | Medium | Low | Test Lambda deployment in sandbox first |
| **CIDR calculation mismatches** | High | Low | Unit test CIDR calculations against Terraform outputs |
| **IAM policy differences** | High | Medium | Compare IAM policies side-by-side, use CDK policy helpers |
| **CloudFormation stack limits** | Medium | Low | Use nested stacks if needed, monitor stack size |
| **Rollback complexity** | High | Low | Keep Terraform codebase until CDK is fully validated |

### 10.2 Rollback Plan

1. **If CDK deployment fails:** Keep Terraform deployment running
2. **If issues discovered post-migration:** Revert to Terraform using existing state
3. **If critical bug found:** Fix in CDK, redeploy, or rollback to Terraform

---

## 11. Success Criteria

- [ ] All Terraform resources have CDK equivalents
- [ ] CDK deployment produces identical infrastructure
- [ ] All Lambda functions work correctly
- [ ] NAT routing functions as expected
- [ ] VPC Flow Logs and CloudWatch logs work
- [ ] Test probes validate connectivity
- [ ] CI/CD pipeline works with CDK
- [ ] Documentation updated
- [ ] Team trained on CDK

---

## 12. Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Setup | 2-3 days | None |
| Phase 2: Networking | 3-4 days | Phase 1 |
| Phase 3: NAT Instances | 4-5 days | Phase 2 |
| Phase 4: Lambda | 3-4 days | Phase 3 |
| Phase 5: Logging | 2-3 days | Phase 2 |
| Phase 6: Probes | 2 days | Phase 2, 3 |
| Phase 7: Integration | 3-4 days | Phases 2-6 |
| Phase 8: CI/CD | 2-3 days | Phase 7 |
| Phase 9: Production | 3-5 days | Phase 8 |
| Phase 10: Cleanup | 1-2 days | Phase 9 |

**Total Estimated Time: 4-6 weeks**

---

## 13. Resources & References

### 13.1 CDK Documentation
- [AWS CDK Python Reference](https://docs.aws.amazon.com/cdk/api/v2/python/)
- [CDK Best Practices](https://docs.aws.amazon.com/cdk/v2/guide/best-practices.html)
- [CDK Patterns](https://github.com/cdk-patterns/serverless)

### 13.2 Migration Guides
- [Terraform to CDK Migration Guide](https://docs.aws.amazon.com/cdk/v2/guide/migrating.html)
- [CDK vs Terraform Comparison](https://aws.amazon.com/blogs/devops/comparing-aws-cdk-and-terraform-for-infrastructure-as-code/)

### 13.3 Tools
- `cdk diff` - Compare deployed stack with current code
- `cdk synth` - Generate CloudFormation template
- `cdk doctor` - Check CDK setup
- `cdk watch` - Watch for changes and deploy

---

## 14. Next Steps

1. **Review this plan** with the team
2. **Set up CDK development environment**
3. **Create feature branch:** `feature/cdk-migration`
4. **Begin Phase 1:** Project setup
5. **Schedule weekly migration reviews**

---

**Document Version:** 1.0
**Last Updated:** 2025-01-XX
**Author:** Migration Planning Team
**Status:** Draft - Pending Review
