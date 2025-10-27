import json
import os
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError


EC2 = boto3.client("ec2")

ROUTE_TABLE_MAP: Dict[str, str] = json.loads(os.environ["ROUTE_TABLE_MAP"])
EIP_MAP: Dict[str, str] = json.loads(os.environ["EIP_MAP"])
PROJECT = os.environ["PROJECT"]
ENVIRONMENT = os.environ["ENVIRONMENT"]


def _describe_primary_eni(instance_id: str) -> str:
    response = EC2.describe_instances(InstanceIds=[instance_id])
    reservations = response.get("Reservations", [])
    if not reservations:
        raise RuntimeError(f"No reservations found for {instance_id}")
    instances = reservations[0].get("Instances", [])
    if not instances:
        raise RuntimeError(f"No instance data for {instance_id}")
    enis = instances[0].get("NetworkInterfaces", [])
    if not enis:
        raise RuntimeError(f"No network interfaces reported for {instance_id}")
    return enis[0]["NetworkInterfaceId"]


def _associate_eip(eni_id: str, allocation_id: str) -> None:
    if not allocation_id:
        return
    EC2.associate_address(
        AllocationId=allocation_id,
        NetworkInterfaceId=eni_id,
        AllowReassociation=True,
    )


def _replace_route(route_table_id: str, eni_id: str) -> None:
    """Ensure the private route table sends 0.0.0.0/0 traffic through the NAT ENI."""
    try:
        EC2.replace_route(
            RouteTableId=route_table_id,
            DestinationCidrBlock="0.0.0.0/0",
            NetworkInterfaceId=eni_id,
        )
    except ClientError as exc:
        error_code = exc.response["Error"].get("Code")
        # When the route is absent (fresh ASG bring-up), fall back to CreateRoute.
        if error_code in {"InvalidRoute.NotFound", "InvalidParameterValue"}:
            EC2.create_route(
                RouteTableId=route_table_id,
                DestinationCidrBlock="0.0.0.0/0",
                NetworkInterfaceId=eni_id,
            )
        else:
            raise


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    detail = event.get("detail", {})
    instance_id = detail.get("EC2InstanceId")
    az = detail.get("AvailabilityZone")

    if not instance_id or not az:
        raise ValueError(f"Missing instance ID or AZ in event: {event}")

    if az not in ROUTE_TABLE_MAP:
        raise ValueError(f"No route table mapping for AZ {az}")

    allocation_id = EIP_MAP.get(az, "")
    try:
        eni_id = _describe_primary_eni(instance_id)
        _associate_eip(eni_id, allocation_id)
        _replace_route(ROUTE_TABLE_MAP[az], eni_id)
    except ClientError as exc:
        raise RuntimeError(f"Failed to prepare NAT instance {instance_id}: {exc}") from exc

    return {
        "project": PROJECT,
        "environment": ENVIRONMENT,
        "instanceId": instance_id,
        "availabilityZone": az,
        "networkInterfaceId": eni_id,
        "associatedAllocationId": allocation_id,
        "routeTableId": ROUTE_TABLE_MAP[az],
    }
