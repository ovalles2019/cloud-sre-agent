"""AWS Trusted Advisor checks (via Support API)."""

from __future__ import annotations

from typing import Any

import structlog

from backend.config import Settings
from backend.tools.demo_data import demo_trusted_advisor_flags

log = structlog.get_logger()


class TrustedAdvisorTool:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        if not settings.demo_mode:
            try:
                import boto3

                self._client = boto3.client("support", region_name="us-east-1")
            except Exception as exc:  # noqa: BLE001
                log.warning("trusted_advisor_unavailable", error=str(exc))

    def get_cost_optimization_flags(self) -> list[dict[str, Any]]:
        if self._client is None:
            return demo_trusted_advisor_flags()

        # Trusted Advisor requires Business/Enterprise support
        try:
            checks = self._client.describe_trusted_advisor_checks(language="en")
            cost_checks = [
                c for c in checks["checks"]
                if "cost" in c.get("category", "").lower() or "utilization" in c.get("name", "").lower()
            ]
            flags: list[dict[str, Any]] = []
            for check in cost_checks[:5]:
                result = self._client.describe_trusted_advisor_check_result(checkId=check["id"])
                status = result["result"]["status"]
                resources = len(result["result"].get("flaggedResources", []))
                flags.append(
                    {
                        "check": check["name"],
                        "status": status,
                        "resources": resources,
                        "estimated_monthly_savings_usd": 0.0,
                    }
                )
            return flags
        except Exception as exc:  # noqa: BLE001
            log.warning("trusted_advisor_query_failed", error=str(exc))
            return demo_trusted_advisor_flags()
