"""AWS Cost Explorer integration."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import structlog

from backend.config import Settings
from backend.models.schemas import CostAnomaly, Severity
from backend.tools.demo_data import demo_cost_anomalies, demo_cost_by_service

log = structlog.get_logger()


class CostExplorerTool:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        if not settings.demo_mode:
            try:
                import boto3

                self._client = boto3.client("ce", region_name=settings.aws_region)
            except Exception as exc:  # noqa: BLE001
                log.warning("cost_explorer_unavailable", error=str(exc))

    def get_mtd_spend(self) -> tuple[float, float]:
        """Return (mtd_spend, prior_period_spend) for delta calculation."""
        if self._client is None:
            by_service = demo_cost_by_service()
            mtd = sum(by_service.values())
            return mtd, mtd * 0.88

        today = date.today()
        month_start = today.replace(day=1)
        prior_start = (month_start - timedelta(days=1)).replace(day=1)
        prior_end = month_start - timedelta(days=1)

        current = self._sum_cost(month_start, today)
        prior = self._sum_cost(prior_start, prior_end)
        return current, prior

    def get_cost_by_service(self) -> dict[str, float]:
        if self._client is None:
            return demo_cost_by_service()

        today = date.today()
        month_start = today.replace(day=1)
        resp = self._client.get_cost_and_usage(
            TimePeriod={"Start": month_start.isoformat(), "End": (today + timedelta(days=1)).isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        out: dict[str, float] = {}
        for result in resp.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                service = group["Keys"][0].replace("Amazon ", "").replace("AWS ", "")
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                out[service] = round(amount, 2)
        return out

    def detect_cost_anomalies(self) -> list[CostAnomaly]:
        if self._client is None:
            return demo_cost_anomalies(self.settings)

        by_service = self.get_cost_by_service()
        anomalies: list[CostAnomaly] = []
        for service, spend in by_service.items():
            baseline = spend * 0.85
            deviation = ((spend - baseline) / max(baseline, 1)) * 100
            if deviation >= self.settings.cost_anomaly_threshold_pct:
                anomalies.append(
                    CostAnomaly(
                        service=service,
                        current_spend_usd=spend,
                        baseline_spend_usd=round(baseline, 2),
                        deviation_pct=round(deviation, 1),
                        period="MTD",
                        severity=Severity.CRITICAL if deviation >= 30 else Severity.WARNING,
                    )
                )
        return anomalies

    def _sum_cost(self, start: date, end: date) -> float:
        assert self._client is not None
        resp = self._client.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": (end + timedelta(days=1)).isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )
        total = 0.0
        for result in resp.get("ResultsByTime", []):
            total += float(result["Total"]["UnblendedCost"]["Amount"])
        return round(total, 2)
