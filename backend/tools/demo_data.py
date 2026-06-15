"""Deterministic demo telemetry when AWS is unavailable."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from backend.config import Settings
from backend.models.schemas import CostAnomaly, MetricAnomaly, Severity


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def demo_metric_anomalies(settings: Settings, lookback_hours: int) -> list[MetricAnomaly]:
    rng = _rng(settings.demo_seed + lookback_hours)
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=lookback_hours)

    scenarios = [
        ("AWS/EC2", "CPUUtilization", {"InstanceId": "i-0a9f3c2e1b8d4f6a7"}, 92.4, 34.1, Severity.CRITICAL),
        ("AWS/RDS", "DatabaseConnections", {"DBInstanceIdentifier": "prod-orders-db"}, 487.0, 210.0, Severity.WARNING),
        ("AWS/Lambda", "Errors", {"FunctionName": "checkout-webhook"}, 38.0, 2.0, Severity.CRITICAL),
        ("AWS/ECS", "MemoryUtilization", {"ClusterName": "api-cluster"}, 88.0, 52.0, Severity.WARNING),
    ]

    anomalies: list[MetricAnomaly] = []
    for ns, metric, dim, current, baseline, sev in scenarios:
        if rng.random() > 0.15:
            deviation = ((current - baseline) / max(baseline, 1)) * 100
            anomalies.append(
                MetricAnomaly(
                    namespace=ns,
                    metric_name=metric,
                    dimension=dim,
                    current_value=current + rng.uniform(-2, 2),
                    baseline_value=baseline,
                    deviation_pct=round(deviation, 1),
                    period_start=start,
                    period_end=now,
                    severity=sev,
                )
            )
    return anomalies


def demo_cost_anomalies(settings: Settings) -> list[CostAnomaly]:
    rng = _rng(settings.demo_seed + 99)
    rows = [
        ("Amazon EC2", 4280.0, 3120.0, Severity.CRITICAL),
        ("Amazon RDS", 1890.0, 1540.0, Severity.WARNING),
        ("AWS Lambda", 420.0, 380.0, Severity.INFO),
        ("Amazon CloudWatch", 310.0, 180.0, Severity.WARNING),
        ("Amazon S3", 980.0, 920.0, Severity.INFO),
    ]
    anomalies: list[CostAnomaly] = []
    for service, current, baseline, sev in rows:
        deviation = ((current - baseline) / baseline) * 100
        if deviation >= settings.cost_anomaly_threshold_pct or sev == Severity.CRITICAL:
            anomalies.append(
                CostAnomaly(
                    service=service,
                    current_spend_usd=current + rng.uniform(-20, 20),
                    baseline_spend_usd=baseline,
                    deviation_pct=round(deviation, 1),
                    period="MTD",
                    severity=sev,
                )
            )
    return anomalies


def demo_trusted_advisor_flags() -> list[dict]:
    return [
        {
            "check": "Low Utilization Amazon EC2 Instances",
            "status": "warning",
            "resources": 7,
            "estimated_monthly_savings_usd": 640.0,
        },
        {
            "check": "Amazon RDS Idle DB Instances",
            "status": "ok",
            "resources": 0,
            "estimated_monthly_savings_usd": 0.0,
        },
        {
            "check": "Amazon EC2 Reserved Instance Optimization",
            "status": "warning",
            "resources": 3,
            "estimated_monthly_savings_usd": 420.0,
        },
        {
            "check": "Security Groups - Specific Ports Unrestricted",
            "status": "error",
            "resources": 2,
            "estimated_monthly_savings_usd": 0.0,
        },
    ]


def demo_cost_by_service() -> dict[str, float]:
    return {
        "EC2": 4280,
        "RDS": 1890,
        "S3": 980,
        "Lambda": 420,
        "CloudWatch": 310,
        "ECS": 760,
        "ELB": 540,
    }


def demo_sparklines(seed: int) -> dict[str, list[float]]:
    rng = _rng(seed)
    keys = ["cpu", "errors", "latency_p99", "connections", "cost"]
    out: dict[str, list[float]] = {}
    for key in keys:
        base = rng.uniform(20, 60)
        points = [base + rng.uniform(-5, 5) for _ in range(23)]
        points.append(base + rng.uniform(15, 45))
        out[key] = [round(p, 1) for p in points]
    return out
