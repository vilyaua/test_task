"""Main CDK stack for NAT Gateway Alternative."""

import ipaddress
import json
from typing import Dict, Optional, Union

import aws_cdk as cdk
from aws_cdk import aws_autoscaling as autoscaling
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

from cdk.config.prod_config import ProdConfig
from cdk.config.test_config import TestConfig


def calculate_subnet_cidr(vpc_cidr: str, subnet_index: int, newbits: int = 4) -> str:
    """Calculate subnet CIDR equivalent to Terraform cidrsubnet()."""
    network = ipaddress.ip_network(vpc_cidr, strict=False)
    subnets = list(network.subnets(new_prefix=network.prefixlen + newbits))
    if subnet_index >= len(subnets):
        raise ValueError(f"Subnet index {subnet_index} exceeds available subnets")
    return str(subnets[subnet_index])


class NatAlternativeStack(cdk.Stack):
    """CDK Stack for NAT Gateway Alternative infrastructure."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: Union[TestConfig, ProdConfig],
        **kwargs,
    ) -> None:
        """Initialize the NAT Alternative stack."""
        super().__init__(scope, construct_id, **kwargs)

        self.config = config
        self.prefix = config.prefix

        # Create VPC and networking
        self.vpc, self.public_subnets, self.private_subnets = self._create_network()

        # Create KMS keys and logging
        self.logs_kms_key, self.app_logs_kms_key = self._create_logging()

        # Create IAM roles
        self.instance_role = self._create_iam_roles()

        # Create NAT instances
        self.nat_asgs, self.nat_eips, self.nat_sg = self._create_nat_instances()

        # Create Lambda functions
        self.nat_hook_lambda = self._create_lambda_functions()

        # Create test probes
        if config.enable_probes:
            self._create_test_probes()

        # Create outputs
        self._create_outputs()

    def _create_network(  # pylint: disable=too-many-locals
        self,
    ) -> tuple[ec2.Vpc, Dict[str, ec2.CfnSubnet], Dict[str, ec2.CfnSubnet]]:
        """Create VPC, subnets, and route tables."""
        # Create VPC without automatic subnets (we'll create them manually with explicit CIDRs)
        vpc = ec2.Vpc(
            self,
            "NATVpc",
            ip_addresses=ec2.IpAddresses.cidr(self.config.vpc_cidr),
            max_azs=self.config.az_count,
            nat_gateways=0,  # We use NAT instances instead
            enable_dns_hostnames=True,
            enable_dns_support=True,
            subnet_configuration=[],  # No automatic subnets - we create them manually
        )

        cdk.Tags.of(vpc).add("Name", f"{self.prefix}-vpc")

        # Calculate subnet CIDRs (matching Terraform logic)
        public_subnets: Dict[str, ec2.CfnSubnet] = {}
        private_subnets: Dict[str, ec2.CfnSubnet] = {}

        azs = vpc.availability_zones

        # Create Internet Gateway for public subnets
        igw = ec2.CfnInternetGateway(self, "InternetGateway")
        cdk.Tags.of(igw).add("Name", f"{self.prefix}-igw")
        igw_attachment = ec2.CfnVPCGatewayAttachment(
            self, "IGWAttachment", vpc_id=vpc.vpc_id, internet_gateway_id=igw.ref
        )

        for idx, az in enumerate(azs):
            # Public subnet CIDR
            public_cidr = calculate_subnet_cidr(self.config.vpc_cidr, idx, newbits=4)
            # Private subnet CIDR (offset by number of AZs)
            private_cidr = calculate_subnet_cidr(self.config.vpc_cidr, idx + len(azs), newbits=4)

            # Create public subnet using L1 construct with explicit CIDR
            # Note: We'll use CfnSubnet and work around SubnetSelection limitation
            public_subnet_cfn = ec2.CfnSubnet(
                self,
                f"PublicSubnet-{az}",
                vpc_id=vpc.vpc_id,
                availability_zone=az,
                cidr_block=public_cidr,
                map_public_ip_on_launch=True,
                tags=[
                    cdk.CfnTag(key="Name", value=f"{self.prefix}-public-{az}"),
                    cdk.CfnTag(key="Tier", value="public"),
                    cdk.CfnTag(key="kubernetes.io/role/elb", value="1"),
                ],
            )
            public_subnet_cfn.add_dependency(igw_attachment)
            public_subnets[az] = public_subnet_cfn

            # Create public route table
            public_route_table = ec2.CfnRouteTable(
                self,
                f"PublicRouteTable-{az}",
                vpc_id=vpc.vpc_id,
                tags=[
                    cdk.CfnTag(key="Name", value=f"{self.prefix}-public-rt-{az}"),
                    cdk.CfnTag(key="Tier", value="public"),
                ],
            )
            # Add default route to Internet Gateway
            ec2.CfnRoute(
                self,
                f"PublicDefaultRoute-{az}",
                route_table_id=public_route_table.ref,
                destination_cidr_block="0.0.0.0/0",
                gateway_id=igw.ref,
            ).add_dependency(igw_attachment)
            # Associate public subnet with route table
            ec2.CfnSubnetRouteTableAssociation(
                self,
                f"PublicSubnetRouteTableAssociation-{az}",
                subnet_id=public_subnet_cfn.ref,
                route_table_id=public_route_table.ref,
            )

            # Create private subnet using L1 construct with explicit CIDR
            private_subnet_cfn = ec2.CfnSubnet(
                self,
                f"PrivateSubnet-{az}",
                vpc_id=vpc.vpc_id,
                availability_zone=az,
                cidr_block=private_cidr,
                tags=[
                    cdk.CfnTag(key="Name", value=f"{self.prefix}-private-{az}"),
                    cdk.CfnTag(key="Tier", value="private"),
                    cdk.CfnTag(key="kubernetes.io/role/internal", value="1"),
                ],
            )

            # Create route table for private subnet (explicit, not auto-created)
            private_route_table = ec2.CfnRouteTable(
                self,
                f"PrivateRouteTable-{az}",
                vpc_id=vpc.vpc_id,
                tags=[
                    cdk.CfnTag(key="Name", value=f"{self.prefix}-private-rt-{az}"),
                    cdk.CfnTag(key="Tier", value="private"),
                ],
            )

            # Associate private subnet with custom route table
            ec2.CfnSubnetRouteTableAssociation(
                self,
                f"PrivateSubnetRouteTableAssociation-{az}",
                subnet_id=private_subnet_cfn.ref,
                route_table_id=private_route_table.ref,
            )

            # Store route table reference and CIDR as attributes for later use
            setattr(private_subnet_cfn, "_route_table_id", private_route_table.ref)
            # Construct route table ARN manually (CfnRouteTable doesn't have attr_arn)
            route_table_arn = (
                f"arn:aws:ec2:{self.region}:{self.account}:route-table/{private_route_table.ref}"
            )
            setattr(private_subnet_cfn, "_route_table_arn", route_table_arn)
            setattr(private_subnet_cfn, "ipv4_cidr_block", private_cidr)
            private_subnets[az] = private_subnet_cfn

        return vpc, public_subnets, private_subnets

    def _create_logging(self) -> tuple[Optional[kms.IKey], kms.IKey]:
        """Create KMS keys and CloudWatch log groups."""
        # Determine KMS key for flow logs
        # Note: from_lookup requires account to be set in stack env (region is always set)
        has_account = self.account is not None

        if self.config.logs_kms_key_arn:
            flow_logs_kms = kms.Key.from_key_arn(self, "FlowLogsKMS", self.config.logs_kms_key_arn)
        elif self.config.logs_kms_key_alias and has_account:
            # Only use from_lookup if account is available (required for lookup)
            flow_logs_kms = kms.Key.from_lookup(
                self, "FlowLogsKMS", alias_name=self.config.logs_kms_key_alias
            )
        else:
            # Create new KMS key for flow logs
            # Note: For demo cycles, prefer using an existing key via
            # logs_kms_key_arn or logs_kms_key_alias
            flow_logs_kms = kms.Key(
                self,
                "FlowLogsKMS",
                description=f"KMS key for {self.prefix} VPC flow logs",
                enable_key_rotation=True,
                removal_policy=cdk.RemovalPolicy.RETAIN,  # Don't delete key when stack is destroyed
            )

        # Determine KMS key for app logs
        if self.config.app_logs_kms_key_arn:
            app_logs_kms = kms.Key.from_key_arn(
                self, "AppLogsKMS", self.config.app_logs_kms_key_arn
            )
        elif self.config.app_logs_kms_key_alias and has_account:
            # Only use from_lookup if account is available (required for lookup)
            app_logs_kms = kms.Key.from_lookup(
                self, "AppLogsKMS", alias_name=self.config.app_logs_kms_key_alias
            )
        else:
            # Reuse flow logs KMS key or use default
            app_logs_kms = flow_logs_kms

        # Create CloudWatch log groups
        retention = (
            logs.RetentionDays.ONE_MONTH
            if self.config.flow_log_retention_days >= 30
            else logs.RetentionDays.TWO_WEEKS
        )

        vpc_flow_log_group = logs.LogGroup(
            self,
            "VPCFlowLogs",
            log_group_name=f"/aws/vpc/{self.prefix}",
            retention=retention,
            encryption_key=flow_logs_kms,
        )
        cdk.Tags.of(vpc_flow_log_group).add("Name", f"{self.prefix}-flowlogs")

        app_retention = (
            logs.RetentionDays.TWO_WEEKS
            if self.config.app_log_retention_days >= 14
            else logs.RetentionDays.ONE_WEEK
        )

        nat_log_group = logs.LogGroup(
            self,
            "NATInstancesLogs",
            log_group_name=f"/nat/{self.prefix}/nat",
            retention=app_retention,
            encryption_key=app_logs_kms,
        )
        cdk.Tags.of(nat_log_group).add("Name", f"{self.prefix}-nat-logs")
        cdk.Tags.of(nat_log_group).add("Role", "nat")

        probe_log_group = logs.LogGroup(
            self,
            "ProbeLogs",
            log_group_name=f"/nat/{self.prefix}/probe",
            retention=app_retention,
            encryption_key=app_logs_kms,
        )
        cdk.Tags.of(probe_log_group).add("Name", f"{self.prefix}-probe-logs")
        cdk.Tags.of(probe_log_group).add("Role", "probe")

        # Store log group names for user data
        self.nat_log_group_name = nat_log_group.log_group_name
        self.probe_log_group_name = probe_log_group.log_group_name

        # Create VPC Flow Logs
        flow_log_role = iam.Role(
            self,
            "FlowLogsRole",
            assumed_by=iam.ServicePrincipal("vpc-flow-logs.amazonaws.com"),
        )

        flow_log_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogStream",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                    "logs:PutLogEvents",
                ],
                resources=[vpc_flow_log_group.log_group_arn],
            )
        )

        flow_log_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["logs:CreateLogGroup"],
                resources=[vpc_flow_log_group.log_group_arn],
            )
        )

        self.vpc.add_flow_log(
            "VPCFlowLog",
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(
                vpc_flow_log_group, flow_log_role
            ),
            traffic_type=ec2.FlowLogTrafficType.ALL,
        )

        return flow_logs_kms, app_logs_kms

    def _create_iam_roles(self) -> iam.Role:
        """Create IAM roles for EC2 instances."""
        instance_role = iam.Role(
            self,
            "InstanceRole",
            role_name=f"{self.prefix}-instance-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy"),
            ],
        )
        cdk.Tags.of(instance_role).add("Name", f"{self.prefix}-instance-role")

        # Create instance profile
        instance_profile = iam.CfnInstanceProfile(
            self,
            "InstanceProfile",
            instance_profile_name=f"{self.prefix}-instance-profile",
            roles=[instance_role.role_name],
        )

        self.instance_profile_name = instance_profile.instance_profile_name

        return instance_role

    def _create_nat_instances(
        self,
    ) -> tuple[
        Dict[str, autoscaling.CfnAutoScalingGroup], Dict[str, ec2.CfnEIP], ec2.SecurityGroup
    ]:
        """Create NAT instances with Auto Scaling Groups."""
        # Create security group for NAT instances
        nat_sg = ec2.SecurityGroup(
            self,
            "NATSecurityGroup",
            vpc=self.vpc,
            description="Controls access to NAT instances",
            allow_all_outbound=True,
        )
        cdk.Tags.of(nat_sg).add("Name", f"{self.prefix}-nat-sg")
        cdk.Tags.of(nat_sg).add("Tier", "edge")

        # Allow traffic from private subnets
        for private_subnet in self.private_subnets.values():
            nat_sg.add_ingress_rule(
                ec2.Peer.ipv4(private_subnet.ipv4_cidr_block),
                ec2.Port.all_traffic(),
                "Allow traffic from private subnets",
            )

        # Allow SSH from allowed CIDRs
        if self.config.allowed_ssh_cidrs:
            for ssh_cidr in self.config.allowed_ssh_cidrs:
                nat_sg.add_ingress_rule(
                    ec2.Peer.ipv4(ssh_cidr),
                    ec2.Port.tcp(22),
                    "Admin SSH",
                )

        # Create NAT user data script
        nat_user_data = self._get_nat_user_data()

        # Create launch template
        launch_template = ec2.LaunchTemplate(
            self,
            "NATLaunchTemplate",
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            instance_type=(
                ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.SMALL)
                if self.config.nat_instance_type == "t3.small"
                else ec2.InstanceType(self.config.nat_instance_type)
            ),
            role=self.instance_role,
            security_group=nat_sg,
            user_data=ec2.UserData.custom(nat_user_data),
            require_imdsv2=True,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        self.config.nat_root_volume_size,
                        encrypted=True,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                    ),
                )
            ],
        )

        # Create ASGs and EIPs per AZ
        nat_asgs: Dict[str, autoscaling.CfnAutoScalingGroup] = {}
        nat_eips: Dict[str, ec2.CfnEIP] = {}

        for az, public_subnet in self.public_subnets.items():
            # Create Elastic IP
            eip = ec2.CfnEIP(
                self,
                f"NATEIP-{az}",
                domain="vpc",
            )
            cdk.Tags.of(eip).add("Name", f"{self.prefix}-nat-eip-{az}")
            nat_eips[az] = eip

            # Create Auto Scaling Group
            # Since SubnetSelection doesn't work with L1 CfnSubnet, we'll use
            # CfnAutoScalingGroup (L1) directly to specify subnet ID explicitly
            asg_cfn = autoscaling.CfnAutoScalingGroup(
                self,
                f"NATASG-{az}",
                min_size="1",
                max_size="1",
                desired_capacity="1",
                launch_template=autoscaling.CfnAutoScalingGroup.LaunchTemplateSpecificationProperty(
                    launch_template_id=launch_template.launch_template_id,
                    version=launch_template.latest_version_number,
                ),
                vpc_zone_identifier=[public_subnet.ref],
                health_check_type="EC2",
                health_check_grace_period=60,
                tags=[
                    autoscaling.CfnAutoScalingGroup.TagPropertyProperty(
                        key="Name",
                        value=f"{self.prefix}-nat-{az}",
                        propagate_at_launch=True,
                    ),
                    autoscaling.CfnAutoScalingGroup.TagPropertyProperty(
                        key="Role",
                        value="nat",
                        propagate_at_launch=True,
                    ),
                ],
            )
            # Store the CfnAutoScalingGroup (we'll need to update return type)
            nat_asgs[az] = asg_cfn

        return nat_asgs, nat_eips, nat_sg

    def _get_nat_user_data(self) -> str:
        """Generate NAT instance user data script."""
        # Note: Log group name will be substituted at runtime by Lambda
        return (  # type: ignore[no-any-return]
            """#!/usr/bin/env bash
set -euxo pipefail

# Enable IPv4 forwarding persistently
cat <<'EOT' >/etc/sysctl.d/98-nat.conf
net.ipv4.ip_forward = 1
net.ipv4.conf.all.rp_filter = 0
net.ipv4.conf.default.rp_filter = 0
EOT
sysctl -p /etc/sysctl.d/98-nat.conf

# Install iptables tooling; AL2023 already ships with curl
dnf install -y iptables-nft iptables-services
systemctl enable iptables

# Download CloudWatch agent
curl -fsSL \\
    https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/\\
    amazon-cloudwatch-agent.rpm \\
    -o /tmp/amazon-cloudwatch-agent.rpm
rpm -Uvh /tmp/amazon-cloudwatch-agent.rpm

CW_LOG_GROUP_NAT="""
            + self.nat_log_group_name
            + """"
cat >/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<CONFIG
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/cloud-init-output.log",
            "log_group_name": "${CW_LOG_GROUP_NAT}",
            "log_stream_name": "nat-{instance_id}",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S"
          }
        ]
      }
    }
  }
}
CONFIG

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s
systemctl enable --now amazon-cloudwatch-agent

# Ensure the filter table allows forwarding for traffic traversing the instance
iptables -F FORWARD
iptables -P FORWARD ACCEPT

# Flush existing NAT rules and configure masquerading on the detected default interface
primary_iface=$(ip route show default | awk 'NR==1 {print $5}')
: "${primary_iface:=ens5}"
iptables -t nat -F
iptables -t nat -A POSTROUTING -o "${primary_iface}" -j MASQUERADE

# Persist iptables configuration and reload the service to pick up changes
iptables-save >/etc/sysconfig/iptables
systemctl restart iptables

# Ensure the SSM agent is online for automation
systemctl enable --now amazon-ssm-agent

# Harden SSH if it gets enabled later
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart sshd
"""
        )

    def _create_lambda_functions(self) -> lambda_.Function:
        """Create Lambda functions for NAT automation."""
        # Build route table and EIP maps for Lambda
        route_table_map = {
            az: getattr(private_subnet, "_route_table_id")
            for az, private_subnet in self.private_subnets.items()
        }
        route_table_arns = [
            getattr(private_subnet, "_route_table_arn")
            for private_subnet in self.private_subnets.values()
        ]
        eip_map = {az: eip.attr_allocation_id for az, eip in self.nat_eips.items()}
        # CfnAutoScalingGroup doesn't expose auto_scaling_group_name directly
        # We'll use the logical ID (ref) which will be resolved to the physical name
        asg_names = [asg.ref for asg in self.nat_asgs.values()]

        # Create IAM role for NAT ASG hook Lambda
        nat_hook_role = iam.Role(
            self,
            "NATASGHookRole",
            role_name=f"{self.prefix}-nat-asg-hook-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )
        cdk.Tags.of(nat_hook_role).add("Name", f"{self.prefix}-nat-asg-hook-role")

        # Add basic execution role
        nat_hook_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        # Add custom permissions
        nat_hook_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ec2:DescribeInstances"],
                resources=["*"],
            )
        )

        nat_hook_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ec2:ModifyInstanceAttribute"],
                resources=["*"],
            )
        )

        # Add route table permissions
        nat_hook_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ec2:ReplaceRoute", "ec2:CreateRoute"],
                resources=route_table_arns,
            )
        )

        # Add EIP association permissions
        nat_hook_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ec2:AssociateAddress"],
                resources=["*"],
            )
        )

        # Create Lambda function
        nat_hook_lambda = lambda_.Function(
            self,
            "NATASGHook",
            function_name=f"{self.prefix}-nat-asg-hook",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="main.handler",
            code=lambda_.Code.from_asset("infra/lambda/nat_asg_hook"),
            role=nat_hook_role,
            timeout=cdk.Duration.minutes(1),
            environment={
                "PROJECT": self.config.project,
                "ENVIRONMENT": self.config.environment,
                "ROUTE_TABLE_MAP": json.dumps(route_table_map),
                "EIP_MAP": json.dumps(eip_map),
            },
            tracing=lambda_.Tracing.ACTIVE,
        )
        cdk.Tags.of(nat_hook_lambda).add("Name", f"{self.prefix}-nat-asg-hook")

        # Create CloudWatch log group for Lambda
        lambda_log_group = logs.LogGroup(
            self,
            "NATASGHookLogs",
            log_group_name=f"/aws/lambda/{nat_hook_lambda.function_name}",
            retention=logs.RetentionDays.TWO_WEEKS,
            encryption_key=self.app_logs_kms_key,
        )
        cdk.Tags.of(lambda_log_group).add("Name", f"{self.prefix}-nat-asg-hook-lg")

        # Create EventBridge rule for ASG instance launch
        rule = events.Rule(
            self,
            "NATASGLaunchRule",
            description="Invoke Lambda when NAT ASG instances launch successfully",
            event_pattern=events.EventPattern(
                source=["aws.autoscaling"],
                detail_type=["EC2 Instance Launch Successful"],
                detail={
                    "AutoScalingGroupName": asg_names,
                },
            ),
        )

        rule.add_target(targets.LambdaFunction(nat_hook_lambda))

        # Grant EventBridge permission to invoke Lambda
        nat_hook_lambda.add_permission(
            "AllowEventBridgeInvoke",
            principal=iam.ServicePrincipal("events.amazonaws.com"),
            source_arn=rule.rule_arn,
        )

        # Ensure ASGs depend on Lambda
        for asg in self.nat_asgs.values():
            asg.node.add_dependency(nat_hook_lambda)

        return nat_hook_lambda

    def _create_test_probes(self) -> None:
        """Create test probe instances in private subnets."""
        # Create security group for probes
        probe_sg = ec2.SecurityGroup(
            self,
            "ProbeSecurityGroup",
            vpc=self.vpc,
            description="Allows outbound traffic for NAT connectivity probe instances",
            allow_all_outbound=True,
        )
        cdk.Tags.of(probe_sg).add("Name", f"{self.prefix}-probe-sg")
        cdk.Tags.of(probe_sg).add("Role", "probe")

        # Create probe user data
        probe_user_data = self._get_probe_user_data()

        # Create probe instances
        for az, private_subnet in self.private_subnets.items():
            # Create probe instance using CfnInstance (L1) to specify subnet directly
            # Get AMI ID using L2 helper, then use in L1 construct
            ami = ec2.MachineImage.latest_amazon_linux2023().get_image(self)
            probe = ec2.CfnInstance(
                self,
                f"Probe-{az}",
                image_id=ami.image_id,
                instance_type=(
                    "t3.nano"
                    if self.config.probe_instance_type == "t3.nano"
                    else self.config.probe_instance_type
                ),
                subnet_id=private_subnet.ref,
                security_group_ids=[probe_sg.security_group_id],
                iam_instance_profile=self.instance_profile_name,
                user_data=cdk.Fn.base64(probe_user_data),
                # Note: IMDSv2 is enforced via launch template for NAT instances.
                # For probe instances, IMDSv2 enforcement is optional and can be added later.
                block_device_mappings=[
                    ec2.CfnInstance.BlockDeviceMappingProperty(
                        device_name="/dev/xvda",
                        ebs=ec2.CfnInstance.EbsProperty(
                            volume_size=8,
                            volume_type="gp3",
                            encrypted=True,
                        ),
                    )
                ],
                tags=[
                    cdk.CfnTag(key="Name", value=f"{self.prefix}-probe-{az}"),
                    cdk.CfnTag(key="Role", value="probe"),
                ],
            )

            # Ensure probes depend on NAT ASGs
            for asg in self.nat_asgs.values():
                probe.node.add_dependency(asg)

    def _get_probe_user_data(self) -> str:
        """Generate probe instance user data script."""
        return (  # type: ignore[no-any-return]
            """#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/var/log/nat-probe.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "$(date --iso-8601=seconds) [INFO] Starting NAT connectivity probe"

# Ensure the SSM agent is available for log collection
systemctl enable --now amazon-ssm-agent

# Install minimal tooling for outbound checks (curl ships via curl-minimal)
dnf install -y bind-utils traceroute >/dev/null
# Download CloudWatch agent
curl -fsSL \\
    https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/\\
    amazon-cloudwatch-agent.rpm \\
    -o /tmp/amazon-cloudwatch-agent.rpm
rpm -Uvh /tmp/amazon-cloudwatch-agent.rpm >/dev/null

CW_LOG_GROUP_PROBE="""
            + self.probe_log_group_name
            + """"
cat >/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<CONFIG
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/nat-probe.log",
            "log_group_name": "${CW_LOG_GROUP_PROBE}",
            "log_stream_name": "probe-{instance_id}",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S"
          }
        ]
      }
    }
  }
}
CONFIG

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s
systemctl enable --now amazon-cloudwatch-agent

endpoints=(
  "https://checkip.amazonaws.com"
  "https://aws.amazon.com"
)

for endpoint in "${endpoints[@]}"; do
  if curl --silent --show-error --max-time 10 "${endpoint}" >/tmp/probe.out; then
    echo "$(date --iso-8601=seconds) [INFO] curl ${endpoint} succeeded: $(head -n 1 /tmp/probe.out)"
  else
    echo "$(date --iso-8601=seconds) [ERROR] curl ${endpoint} failed"
    exit 2
  fi
done

if dig +short cloudfront.net >/tmp/dns.out; then
  echo "$(date --iso-8601=seconds) [INFO] DNS lookup succeeded: $(head -n 1 /tmp/dns.out)"
else
  echo "$(date --iso-8601=seconds) [ERROR] DNS lookup failed"
  exit 3
fi

echo "$(date --iso-8601=seconds) [INFO] Traceroute sample to 1.1.1.1"
traceroute -w 2 -q 1 1.1.1.1 | head -n 10

echo "$(date --iso-8601=seconds) [INFO] NAT connectivity probe completed successfully; entering standby for health monitoring"

# Keep instance online for subsequent health checks and log collection.
while true; do
  echo "$(date --iso-8601=seconds) [INFO] Heartbeat: probe instance idle" >>"${LOG_FILE}"
  sleep 5
done
"""
        )

    def _create_outputs(self) -> None:
        """Create CloudFormation outputs."""
        cdk.CfnOutput(
            self,
            "VpcId",
            description="Identifier for the NAT alternative VPC",
            value=self.vpc.vpc_id,
        )

        # Output subnet IDs
        for az, subnet in self.public_subnets.items():
            cdk.CfnOutput(
                self,
                f"PublicSubnetId-{az}",
                description=f"Public subnet ID for {az}",
                value=subnet.ref,  # L1 CfnSubnet uses .ref for subnet ID
            )

        for az, subnet in self.private_subnets.items():
            cdk.CfnOutput(
                self,
                f"PrivateSubnetId-{az}",
                description=f"Private subnet ID for {az}",
                value=subnet.ref,  # L1 CfnSubnet uses .ref for subnet ID
            )

        # Output NAT EIP addresses
        for az, eip in self.nat_eips.items():
            cdk.CfnOutput(
                self,
                f"NATEIPOutput-{az}",  # Different ID from EIP construct to avoid duplicate
                description=f"Elastic IP for NAT instance in {az}",
                value=eip.attr_public_ip,
            )
