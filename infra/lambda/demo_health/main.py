"""Lambda to report demo health (instances, SSM, logs)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import boto3
from botocore.exceptions import BotoCoreError, ClientError

REGION = os.environ["AWS_REGION"]
PROJECT = os.environ.get("PROJECT_TAG", "nat-alternative")
ENVIRONMENT = os.environ.get("ENVIRONMENT_TAG", "test")
LOOKBACK_MINUTES = int(os.environ.get("LOOKBACK_MINUTES", "15"))
MAX_LOG_EVENTS = int(os.environ.get("MAX_LOG_EVENTS", "50"))


_ec2 = boto3.client("ec2", region_name=REGION)
_ssm = boto3.client("ssm", region_name=REGION)
_logs = boto3.client("logs", region_name=REGION)
_lambda = boto3.client("lambda", region_name=REGION)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _describe_instances(role: str) -> List[Dict[str, Any]]:
    filters = [
        {"Name": "tag:Project", "Values": [PROJECT]},
        {"Name": "tag:Environment", "Values": [ENVIRONMENT]},
        {"Name": "tag:Role", "Values": [role]},
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
    ]
    resp = _ec2.describe_instances(Filters=filters)
    details: List[Dict[str, Any]] = []
    for reservation in resp.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            instance_id = instance["InstanceId"]
            state = instance.get("State", {}).get("Name")
            az = instance.get("Placement", {}).get("AvailabilityZone")
            details.append(
                {
                    "instanceId": instance_id,
                    "state": state,
                    "availabilityZone": az,
                    "launchTime": _iso(instance["LaunchTime"]),
                }
            )
    return details


def _ssm_status(instance_ids: List[str]) -> Dict[str, str]:
    status: Dict[str, str] = {instance_id: "Unknown" for instance_id in instance_ids}
    if not instance_ids:
        return status

    paginator = _ssm.get_paginator("describe_instance_information")
    for page in paginator.paginate():
        for item in page.get("InstanceInformationList", []):
            instance_id = item.get("InstanceId")
            if instance_id in status:
                status[instance_id] = item.get("PingStatus", "Unknown")
    return status


def _log_group_status(names: List[str]) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []
    for name in names:
        status = {
            "logGroup": name,
            "exists": True,
            "latestEventTime": None,
            "streams": [],
        }

        try:
            streams = _logs.describe_log_streams(
                logGroupName=name,
                orderBy="LastEventTime",
                descending=True,
                limit=3,
            ).get("logStreams", [])
        except ClientError as exc:  # pylint: disable=duplicate-code
            error_code = exc.response["Error"].get("Code")
            if error_code == "ResourceNotFoundException":
                status.update({"exists": False, "error": exc.response["Error"].get("Message", str(exc))})
            else:
                status.update({"error": exc.response["Error"].get("Message", str(exc))})
            summary.append(status)
            continue

        for stream in streams:
            stream_info = {
                "logStream": stream.get("logStreamName"),
                "storedBytes": stream.get("storedBytes", 0),
                "lastEventTimestamp": stream.get("lastEventTimestamp"),
                "creationTime": stream.get("creationTime"),
            }
            if stream_info["lastEventTimestamp"]:
                status["latestEventTime"] = _iso(datetime.fromtimestamp(stream_info["lastEventTimestamp"] / 1000, tz=timezone.utc))
            status["streams"].append(stream_info)
        summary.append(status)
    return summary


def _invoke_log_collector(function_name: str) -> Dict[str, Any]:
    try:
        response = _lambda.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps({
                "lookback_minutes": LOOKBACK_MINUTES,
                "max_events": MAX_LOG_EVENTS,
            }).encode("utf-8"),
        )
    except (ClientError, BotoCoreError) as exc:
        return {"error": str(exc)}

    payload = response.get("Payload")
    if payload is None:
        return {"error": "No payload returned"}

    body = payload.read().decode("utf-8")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw": body}


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    # Allow override via event
    function_name = event.get("log_collector_function") or os.environ.get("LOG_COLLECTOR_FUNCTION", "")
    lookback_minutes = int(event.get("lookback_minutes", LOOKBACK_MINUTES))

    nat_instances = _describe_instances("nat")
    probe_instances = _describe_instances("probe")

    nat_ssm = _ssm_status([inst["instanceId"] for inst in nat_instances])
    probe_ssm = _ssm_status([inst["instanceId"] for inst in probe_instances])

    log_groups = [
        f"/aws/vpc/{PROJECT}-{ENVIRONMENT}",
        f"/nat/{PROJECT}-{ENVIRONMENT}/nat",
        f"/nat/{PROJECT}-{ENVIRONMENT}/probe",
        f"/aws/lambda/{PROJECT}-{ENVIRONMENT}-log-collector",
    ]

    log_status = _log_group_status(log_groups)

    collector_result = None
    if function_name:
        collector_result = _invoke_log_collector(function_name)

    return {
        "generatedAt": _iso(datetime.now(timezone.utc)),
        "project": PROJECT,
        "environment": ENVIRONMENT,
        "lookbackMinutes": lookback_minutes,
        "natInstances": [
            {
                **inst,
                "ssmPingStatus": nat_ssm.get(inst["instanceId"], "Unknown"),
            }
            for inst in nat_instances
        ],
        "probeInstances": [
            {
                **inst,
                "ssmPingStatus": probe_ssm.get(inst["instanceId"], "Unknown"),
            }
            for inst in probe_instances
        ],
        "logGroups": log_status,
        "logCollector": collector_result,
    }


if __name__ == "__main__":
    print(json.dumps(handler({}, None), indent=2))
