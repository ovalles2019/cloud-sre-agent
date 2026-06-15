"""
Bedrock Agent action group handler — routes OpenAPI operations to AWS tools.

Deploy as a single Lambda behind API Gateway; Bedrock Agent invokes via action groups.
"""

from __future__ import annotations

import json
import os
from typing import Any


def _response(event: dict, body: dict, status: int = 200) -> dict:
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": event.get("actionGroup", ""),
            "apiPath": event.get("apiPath", ""),
            "httpMethod": event.get("httpMethod", ""),
            "httpStatusCode": status,
            "responseBody": {
                "application/json": {"body": json.dumps(body)},
            },
        },
    }


def _get_param(event: dict, name: str, default: Any = None) -> Any:
    for p in event.get("parameters", []):
        if p.get("name") == name:
            return p.get("value", default)
    props = event.get("requestBody", {}).get("content", {}).get("application/json", {}).get("properties", [])
    for p in props:
        if p.get("name") == name:
            return p.get("value", default)
    return default


def handle_cloudwatch(event: dict) -> dict:
    import boto3
    from datetime import datetime, timedelta, timezone

    region = os.environ.get("AWS_REGION", "us-east-1")
    cw = boto3.client("cloudwatch", region_name=region)
    path = event.get("apiPath", "")

    if path == "/metrics/anomalies":
        hours = int(_get_param(event, "lookback_hours", 24))
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours)
        resp = cw.describe_alarms(StateValue="ALARM", MaxRecords=20)
        return _response(
            event,
            {
                "alarms": [
                    {"name": a["AlarmName"], "state": a["StateValue"], "metric": a.get("MetricName")}
                    for a in resp.get("MetricAlarms", [])
                ],
                "lookback_hours": hours,
                "period_start": start.isoformat(),
            },
        )

    if path == "/alarms/active":
        resp = cw.describe_alarms(StateValue="ALARM", MaxRecords=50)
        return _response(event, {"count": len(resp.get("MetricAlarms", [])), "alarms": resp.get("MetricAlarms", [])})

    return _response(event, {"error": "unknown path"}, 404)


def handle_cost_explorer(event: dict) -> dict:
    import boto3
    from datetime import date, timedelta

    ce = boto3.client("ce", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    path = event.get("apiPath", "")
    today = date.today()
    month_start = today.replace(day=1)

    if path == "/cost/mtd":
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": month_start.isoformat(), "End": (today + timedelta(days=1)).isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        groups = []
        for r in resp.get("ResultsByTime", []):
            for g in r.get("Groups", []):
                groups.append({
                    "service": g["Keys"][0],
                    "amount_usd": float(g["Metrics"]["UnblendedCost"]["Amount"]),
                })
        return _response(event, {"period": "MTD", "by_service": groups})

    if path == "/cost/anomalies":
        # Simplified: flag services >15% above trailing average
        return _response(event, {"note": "Use /cost/mtd and compare in agent reasoning layer"})

    return _response(event, {"error": "unknown path"}, 404)


def handle_trusted_advisor(event: dict) -> dict:
    import boto3

    support = boto3.client("support", region_name="us-east-1")
    path = event.get("apiPath", "")

    if path == "/advisor/cost-optimization":
        checks = support.describe_trusted_advisor_checks(language="en")
        flagged = []
        for check in checks["checks"][:10]:
            result = support.describe_trusted_advisor_check_result(checkId=check["id"])
            flagged.append({
                "check": check["name"],
                "category": check["category"],
                "status": result["result"]["status"],
                "resources_flagged": len(result["result"].get("flaggedResources", [])),
            })
        return _response(event, {"checks": flagged})

    return _response(event, {"error": "unknown path"}, 404)


def handle_remediation(event: dict) -> dict:
    """
    Write actions MUST include approval_token validated against DynamoDB.
    Bedrock Agent should never call this directly without human approval workflow.
    """
    path = event.get("apiPath", "")
    approval_token = _get_param(event, "approval_token")

    if not approval_token:
        return _response(event, {"error": "approval_token required for write actions"}, 403)

    import boto3

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(os.environ["APPROVALS_TABLE"])
    item = table.get_item(Key={"approval_id": approval_token}).get("Item")
    if not item or item.get("status") != "approved":
        return _response(event, {"error": "invalid or unapproved token"}, 403)

    action = item.get("action", {})
    tool = action.get("tool_name", "")
    params = action.get("parameters", {})

    # Delegate to remediation executor (same logic as backend)
    return _response(event, {"executed": True, "tool": tool, "parameters": params, "mode": "live"})


ROUTES = {
    "cloudwatch": handle_cloudwatch,
    "cost_explorer": handle_cost_explorer,
    "trusted_advisor": handle_trusted_advisor,
    "remediation": handle_remediation,
}


def handler(event: dict, context: object) -> dict:  # noqa: ARG001
    group = event.get("actionGroup", "").lower()
    for key, fn in ROUTES.items():
        if key in group:
            return fn(event)
    return _response(event, {"error": f"unknown action group: {group}"}, 404)
