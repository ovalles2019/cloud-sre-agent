"""OpenAPI schema for Bedrock Agent action groups."""

OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "Cloud SRE Agent Tools", "version": "1.0.0"},
    "paths": {
        "/metrics/anomalies": {
            "get": {
                "operationId": "getMetricAnomalies",
                "description": "Detect CloudWatch metric anomalies vs baseline window",
                "parameters": [
                    {"name": "lookback_hours", "in": "query", "schema": {"type": "integer"}, "required": False}
                ],
            }
        },
        "/alarms/active": {
            "get": {
                "operationId": "getActiveAlarms",
                "description": "List CloudWatch alarms in ALARM state",
            }
        },
        "/cost/mtd": {
            "get": {
                "operationId": "getMtdCost",
                "description": "Get month-to-date spend grouped by AWS service",
            }
        },
        "/cost/anomalies": {
            "get": {
                "operationId": "getCostAnomalies",
                "description": "Detect cost anomalies vs baseline",
            }
        },
        "/advisor/cost-optimization": {
            "get": {
                "operationId": "getTrustedAdvisorCostChecks",
                "description": "Retrieve Trusted Advisor cost optimization flags",
            }
        },
        "/remediate/execute": {
            "post": {
                "operationId": "executeRemediation",
                "description": "Execute an approved remediation action (requires approval_token)",
                "parameters": [
                    {"name": "approval_token", "in": "query", "schema": {"type": "string"}, "required": True}
                ],
            }
        },
    },
}
