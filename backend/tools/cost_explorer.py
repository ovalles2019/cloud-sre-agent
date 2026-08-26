"""AWS Cost Explorer integration."""

from __future__ import annotations

from datetime import date, timedelta

import structlog

from backend.config import Settings
from backend.models.schemas import CostAnomaly, Severity
from backend.tools.demo_data import demo_cost_anomalies, demo_cost_by_service

log = structlog.get_logger()


def _service_label(raw: str) -> str:
    return raw.replace("Amazon ", "").replace("AWS ", "")


def equivalent_windows(today: date | None = None) -> tuple[date, date, date, date]:
    """MTD window vs the same number of days in the prior month.

    Returns (current_start, current_end, prior_start, prior_end), all inclusive.
    """
    today = today or date.today()
    current_start = today.replace(day=1)
    elapsed = (today - current_start).days + 1
    prior_month_last = current_start - timedelta(days=1)
    prior_start = prior_month_last.replace(day=1)
    prior_end = prior_start + timedelta(days=elapsed - 1)
    if prior_end > prior_month_last:
        prior_end = prior_month_last
    return current_start, today, prior_start, prior_end


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
        """Return (mtd_spend, prior_equivalent_window_spend) for delta calculation."""
        if self._client is None:
            by_service = demo_cost_by_service()
            mtd = sum(by_service.values())
            return mtd, mtd * 0.88

        current_start, current_end, prior_start, prior_end = equivalent_windows()
        current = self._sum_cost(current_start, current_end)
        prior = self._sum_cost(prior_start, prior_end)
        return current, prior

    def get_cost_by_service(self) -> dict[str, float]:
        if self._client is None:
            return demo_cost_by_service()

        current_start, current_end, _, _ = equivalent_windows()
        return self._cost_by_service(current_start, current_end)

    def detect_cost_anomalies(self) -> list[CostAnomaly]:
        if self._client is None:
            return demo_cost_anomalies(self.settings)

        current_start, current_end, prior_start, prior_end = equivalent_windows()
        current = self._cost_by_service(current_start, current_end)
        prior = self._cost_by_service(prior_start, prior_end)
        period = f"{current_start.isoformat()}–{current_end.isoformat()} vs prior"

        anomalies: list[CostAnomaly] = []
        threshold = self.settings.cost_anomaly_threshold_pct
        for service, spend in current.items():
            baseline = prior.get(service, 0.0)
            if baseline <= 0:
                # New service with no comparable prior window — skip noise.
                continue
            deviation = ((spend - baseline) / baseline) * 100
            if deviation >= threshold:
                anomalies.append(
                    CostAnomaly(
                        service=service,
                        current_spend_usd=round(spend, 2),
                        baseline_spend_usd=round(baseline, 2),
                        deviation_pct=round(deviation, 1),
                        period=period,
                        severity=Severity.CRITICAL if deviation >= 30 else Severity.WARNING,
                    )
                )
        return anomalies

    def _cost_by_service(self, start: date, end: date) -> dict[str, float]:
        assert self._client is not None
        resp = self._client.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": (end + timedelta(days=1)).isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        out: dict[str, float] = {}
        for result in resp.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                service = _service_label(group["Keys"][0])
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                out[service] = round(out.get(service, 0.0) + amount, 2)
        return out

    def _sum_cost(self, start: date, end: date) -> float:
        assert self._client is not None
        resp = self._client.get_cost_and_usage(
            TimePeriod={"Start": start.isoformat(), "End": (end + timedelta(days=1)).isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
        )
        total = 0.0
        for result in resp.get("ResultsByTime", []):
            total += float(result["Total"]["UnblendedCost"]["Amount"])
        return round(total, 2)
