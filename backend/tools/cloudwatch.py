"""CloudWatch metrics and alarms queries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from backend.config import Settings
from backend.models.schemas import MetricAnomaly, Severity
from backend.tools.demo_data import demo_metric_anomalies

log = structlog.get_logger()


class CloudWatchTool:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        if not settings.demo_mode:
            try:
                import boto3

                self._client = boto3.client("cloudwatch", region_name=settings.aws_region)
            except Exception as exc:  # noqa: BLE001
                log.warning("cloudwatch_client_unavailable", error=str(exc))

    def get_active_alarms(self) -> list[dict[str, Any]]:
        if self._client is None:
            return [
                {"name": "prod-api-cpu-high", "state": "ALARM", "metric": "CPUUtilization"},
                {"name": "checkout-lambda-errors", "state": "ALARM", "metric": "Errors"},
                {"name": "rds-connections-high", "state": "OK", "metric": "DatabaseConnections"},
            ]

        resp = self._client.describe_alarms(StateValue="ALARM", MaxRecords=50)
        return [
            {
                "name": a["AlarmName"],
                "state": a["StateValue"],
                "metric": a.get("MetricName", ""),
            }
            for a in resp.get("MetricAlarms", [])
        ]

    def detect_metric_anomalies(self, lookback_hours: int = 24) -> list[MetricAnomaly]:
        if self._client is None:
            return demo_metric_anomalies(self.settings, lookback_hours)

        # Production path: sample key metrics and compare to prior window
        anomalies: list[MetricAnomaly] = []
        now = datetime.now(timezone.utc)
        end = now
        start = now - timedelta(hours=lookback_hours)
        prior_end = start
        prior_start = start - timedelta(hours=lookback_hours)

        queries = [
            ("AWS/EC2", "CPUUtilization", "Average"),
            ("AWS/Lambda", "Errors", "Sum"),
            ("AWS/RDS", "DatabaseConnections", "Average"),
        ]
        for namespace, metric, stat in queries:
            current = self._avg_metric(namespace, metric, start, end, stat)
            baseline = self._avg_metric(namespace, metric, prior_start, prior_end, stat)
            if baseline <= 0:
                continue
            deviation = ((current - baseline) / baseline) * 100
            if abs(deviation) >= 20:
                anomalies.append(
                    MetricAnomaly(
                        namespace=namespace,
                        metric_name=metric,
                        current_value=round(current, 2),
                        baseline_value=round(baseline, 2),
                        deviation_pct=round(deviation, 1),
                        period_start=start,
                        period_end=end,
                        severity=Severity.CRITICAL if abs(deviation) >= 50 else Severity.WARNING,
                    )
                )
        return anomalies

    def _avg_metric(
        self,
        namespace: str,
        metric: str,
        start: datetime,
        end: datetime,
        stat: str,
    ) -> float:
        assert self._client is not None
        resp = self._client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric,
            StartTime=start,
            EndTime=end,
            Period=3600,
            Statistics=[stat],
        )
        points = resp.get("Datapoints", [])
        if not points:
            return 0.0
        return sum(p[stat] for p in points) / len(points)
