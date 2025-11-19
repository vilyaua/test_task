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

    def _create_network(
        self,
    ) -> tuple[ec2.Vpc, Dict[str, ec2.PublicSubnet], Dict[str, ec2.PrivateSubnet]]:
        """Create VPC, subnets, and route tables."""
        # Create VPC
        vpc = ec2.Vpc(
            self,
            "NATVpc",
            ip_addresses=ec2.IpAddresses.cidr(self.config.vpc_cidr),
            max_azs=self.config.az_count,
            nat_gateways=0,  # We use NAT instances instead
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )

        cdk.Tags.of(vpc).add("Name", f"{self.prefix}-vpc")

        # Calculate subnet CIDRs (matching Terraform logic)
        public_subnets: Dict[str, ec2.PublicSubnet] = {}
        private_subnets: Dict[str, ec2.PrivateSubnet] = {}

        azs = vpc.availability_zones
        for idx, az in enumerate(azs):
            # Public subnet CIDR
            public_cidr = calculate_subnet_cidr(self.config.vpc_cidr, idx, newbits=4)
            # Private subnet CIDR (offset by number of AZs)
            private_cidr = calculate_subnet_cidr(self.config.vpc_cidr, idx + len(azs), newbits=4)

            # Create public subnet
            public_subnet = ec2.PublicSubnet(
                self,
                f"PublicSubnet-{az}",
                vpc=vpc,
                availability_zone=az,
                cidr_block=public_cidr,
                map_public_ip_on_launch=True,
            )
            cdk.Tags.of(public_subnet).add("Name", f"{self.prefix}-public-{az}")
            cdk.Tags.of(public_subnet).add("Tier", "public")
            cdk.Tags.of(public_subnet).add("kubernetes.io/role/elb", "1")
            public_subnets[az] = public_subnet

            # Create private subnet with explicit route table
            # Create route table for private subnet
            private_route_table = ec2.CfnRouteTable(
                self,
                f"PrivateRouteTable-{az}",
                vpc_id=vpc.vpc_id,
            )
            cdk.Tags.of(private_route_table).add("Name", f"{self.prefix}-private-rt-{az}")
            cdk.Tags.of(private_route_table).add("Tier", "private")

            # Create private subnet
            private_subnet = ec2.PrivateSubnet(
                self,
                f"PrivateSubnet-{az}",
                vpc=vpc,
                availability_zone=az,
                cidr_block=private_cidr,
            )
            cdk.Tags.of(private_subnet).add("Name", f"{self.prefix}-private-{az}")
            cdk.Tags.of(private_subnet).add("Tier", "private")
            cdk.Tags.of(private_subnet).add("kubernetes.io/role/internal", "1")

            # Associate route table with subnet
            ec2.CfnSubnetRouteTableAssociation(
                self,
                f"PrivateSubnetRouteTableAssociation-{az}",
                subnet_id=private_subnet.subnet_id,
                route_table_id=private_route_table.ref,
            )

            # Store route table reference as attributes
            # We'll access these via a wrapper
            setattr(private_subnet, "_route_table_id", private_route_table.ref)
            setattr(private_subnet, "_route_table_arn", private_route_table.attr_arn)
            private_subnets[az] = private_subnet

        return vpc, public_subnets, private_subnets

    def _create_logging(self) -> tuple[Optional[kms.IKey], kms.IKey]:
        """Create KMS keys and CloudWatch log groups."""
        # Determine KMS key for flow logs
        if self.config.logs_kms_key_arn:
            flow_logs_kms = kms.Key.from_key_arn(self, "FlowLogsKMS", self.config.logs_kms_key_arn)
        elif self.config.logs_kms_key_alias:
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
        elif self.config.app_logs_kms_key_alias:
            app_logs_kms = kms.Key.from_lookup(
                self, "AppLogsKMS", alias_name=self.config.app_logs_kms_key_alias
            )
        else:
            # Reuse flow logs KMS key or use default
            app_logs_kms = flow_logs_kms

        # Create CloudWatch log groups
        retention = (
            logs.RetentionDays.THIRTY_DAYS
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
    ) -> tuple[Dict[str, autoscaling.AutoScalingGroup], Dict[str, ec2.CfnEIP], ec2.SecurityGroup]:
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
        nat_asgs: Dict[str, autoscaling.AutoScalingGroup] = {}
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
            asg = autoscaling.AutoScalingGroup(
                self,
                f"NATASG-{az}",
                vpc=self.vpc,
                vpc_subnets=ec2.SubnetSelection(subnets=[public_subnet]),
                launch_template=launch_template,
                min_capacity=1,
                max_capacity=1,
                desired_capacity=1,
                health_check=autoscaling.HealthCheck.ec2(),
                health_check_grace_period=cdk.Duration.minutes(1),
            )
            cdk.Tags.of(asg).add("Name", f"{self.prefix}-nat-{az}")
            cdk.Tags.of(asg).add("Role", "nat")
            nat_asgs[az] = asg

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
        asg_names = [asg.auto_scaling_group_name for asg in self.nat_asgs.values()]

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
            probe = ec2.Instance(
                self,
                f"Probe-{az}",
                vpc=self.vpc,
                vpc_subnets=ec2.SubnetSelection(subnets=[private_subnet]),
                instance_type=(
                    ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.NANO)
                    if self.config.probe_instance_type == "t3.nano"
                    else ec2.InstanceType(self.config.probe_instance_type)
                ),
                machine_image=ec2.MachineImage.latest_amazon_linux2023(),
                security_group=probe_sg,
                role=self.instance_role,
                user_data=ec2.UserData.custom(probe_user_data),
                require_imdsv2=True,
                block_devices=[
                    ec2.BlockDevice(
                        device_name="/dev/xvda",
                        volume=ec2.BlockDeviceVolume.ebs(
                            8,
                            encrypted=True,
                            volume_type=ec2.EbsDeviceVolumeType.GP3,
                        ),
                    )
                ],
            )
            cdk.Tags.of(probe).add("Name", f"{self.prefix}-probe-{az}")
            cdk.Tags.of(probe).add("Role", "probe")

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
                value=subnet.subnet_id,
            )

        for az, subnet in self.private_subnets.items():
            cdk.CfnOutput(
                self,
                f"PrivateSubnetId-{az}",
                description=f"Private subnet ID for {az}",
                value=subnet.subnet_id,
            )

        # Output NAT EIP addresses
        for az, eip in self.nat_eips.items():
            cdk.CfnOutput(
                self,
                f"NATEIP-{az}",
                description=f"Elastic IP for NAT instance in {az}",
                value=eip.attr_public_ip,
            )
