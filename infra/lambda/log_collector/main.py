import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError


logs_client = boto3.client("logs")

DEFAULT_LOOKBACK_MINUTES = int(os.getenv("LOOKBACK_MINUTES", "15"))
DEFAULT_MAX_EVENTS = int(os.getenv("MAX_EVENTS", "200"))
DEFAULT_LOG_GROUPS = [group for group in os.getenv("LOG_GROUPS", "").split(",") if group]


def _isoformat(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def _collect_events(log_group: str, start_time_ms: int, max_events: int) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    next_token = None

    while len(events) < max_events:
        limit = min(10000, max_events - len(events))
        if limit <= 0:
            break

        params: Dict[str, Any] = {
            "logGroupName": log_group,
            "startTime": start_time_ms,
            "limit": limit,
        }
        if next_token is not None:
            params["nextToken"] = next_token

        response = logs_client.filter_log_events(**params)
        events.extend(response.get("events", []))
        next_token = response.get("nextToken")

        if not next_token:
            break

    # Deduplicate while preserving order
    seen = set()
    unique_events: List[Dict[str, Any]] = []
    for event in events[-max_events:]:
        key = (event.get("eventId"), event.get("timestamp"), event.get("logStreamName"))
        if key in seen:
            continue
        seen.add(key)
        unique_events.append(event)

    return unique_events


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    event = event or {}

    lookback_minutes = int(event.get("lookback_minutes", DEFAULT_LOOKBACK_MINUTES))
    max_events = int(event.get("max_events", DEFAULT_MAX_EVENTS))

    log_groups = event.get("log_groups") or DEFAULT_LOG_GROUPS
    if not log_groups:
        raise ValueError("No log groups provided via event.log_groups or LOG_GROUPS environment variable.")

    since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
    start_time_ms = int(since.timestamp() * 1000)

    payload: Dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "lookbackMinutes": lookback_minutes,
        "maxEvents": max_events,
        "logGroups": [],
    }

    for log_group in log_groups:
        try:
            group_events = _collect_events(log_group, start_time_ms, max_events)
        except ClientError as exc:
            payload["logGroups"].append(
                {
                    "logGroup": log_group,
                    "error": exc.response["Error"].get("Message", str(exc)),
                }
            )
            continue

        payload["logGroups"].append(
            {
                "logGroup": log_group,
                "eventCount": len(group_events),
                "events": [
                    {
                        "timestamp": _isoformat(event["timestamp"]),
                        "message": event.get("message", ""),
                        "logStream": event.get("logStreamName", ""),
                    }
                    for event in group_events
                ],
            }
        )

    return payload


if __name__ == "__main__":
    print(json.dumps(handler({}, None), indent=2))
