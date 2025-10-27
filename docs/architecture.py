"""
Generates the NAT alternative architecture diagram using mingrammer's Diagrams.

Run from the repository root (after `pip install diagrams`):

    python docs/architecture.py

This will produce docs/architecture.png without opening a viewer.
"""

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import AutoScaling, EC2, Lambda
from diagrams.aws.integration import Eventbridge
from diagrams.aws.management import Cloudwatch, SystemsManager
from diagrams.aws.network import InternetGateway, PublicSubnet, PrivateSubnet, RouteTable, VPC
from diagrams.aws.security import IAM


with Diagram(
    "NAT Alternative Architecture",
    filename="docs/architecture",
    outformat="png",
    show=False,
):
    internet = InternetGateway("Internet")

    with Cluster("NAT Environment (eu-central-1)"):
        vpc = VPC("VPC 10.0.0.0/16")

        with Cluster("Public Subnets (AZ-a / AZ-b)"):
            pub_subnets = [
                PublicSubnet("Public AZ-a\n10.0.16.0/20"),
                PublicSubnet("Public AZ-b\n10.0.32.0/20"),
            ]
            nat_asg = AutoScaling("NAT ASG\n(1 per AZ)")
            nat_instances = [
                EC2("NAT Instance\nAZ-a"),
                EC2("NAT Instance\nAZ-b"),
            ]
            nat_asg >> nat_instances
            for subnet, nat in zip(pub_subnets, nat_instances):
                subnet >> nat
                nat >> Edge(color="black") >> internet

        with Cluster("Private Subnets (AZ-a / AZ-b)"):
            private_subnets = [
                PrivateSubnet("Private AZ-a\n10.0.48.0/20"),
                PrivateSubnet("Private AZ-b\n10.0.64.0/20"),
            ]
            private_routes = RouteTable("Private Route Tables\n(0.0.0.0/0 → NAT)")
            probes = [
                EC2("Probe Instance\nAZ-a"),
                EC2("Probe Instance\nAZ-b"),
            ]
            for subnet, probe in zip(private_subnets, probes):
                subnet >> probe >> private_routes
            private_routes >> nat_instances

    # Automation components outside the VPC cluster for clarity.
    hook_lambda = Lambda("nat-asg-hook\n(Lambda)")
    log_collector = Lambda("log-collector")
    demo_health = Lambda("demo-health")
    event_rule = Eventbridge("EC2 Launch\nEventBridge Rule")
    iam_instance_role = IAM("Instance Role\n(AmazonSSM + CW Agent)")
    cloudwatch_logs = Cloudwatch("CloudWatch Logs\n(Flow/NAT/Probe)")
    systems_manager = SystemsManager("AWS Systems Manager\n(SSM)")

    # Event-driven automation
    nat_asg >> Edge(label="Launch lifecycle", color="royalblue") >> event_rule
    event_rule >> Edge(label="Invoke", style="dashed") >> hook_lambda
    hook_lambda >> Edge(label="Disable source/dest\nAssociate EIP") >> nat_instances
    hook_lambda >> Edge(label="Update routes") >> private_routes

    # Observability and health
    nat_instances >> Edge(label="Flow/NAT logs") >> cloudwatch_logs
    probes >> Edge(label="Probe logs") >> cloudwatch_logs
    cloudwatch_logs >> Edge(label="Fetch", color="darkgreen") >> log_collector
    log_collector >> Edge(label="Summaries") >> demo_health
    demo_health >> Edge(label="Health JSON") >> systems_manager

    # SSM connectivity
    iam_instance_role >> nat_instances
    iam_instance_role >> probes
    nat_instances >> Edge(label="SSM Agent") >> systems_manager
    probes >> Edge(label="SSM Agent") >> systems_manager

