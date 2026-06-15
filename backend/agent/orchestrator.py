"""Bedrock-powered SRE agent orchestrator."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

import structlog

from backend.config import Settings
from backend.models.schemas import (
    ActionRisk,
    AgentTraceStep,
    CostAnomaly,
    IncidentReport,
    IncidentStatus,
    MetricAnomaly,
    RecommendedAction,
    RunAnalysisRequest,
    Severity,
)
from backend.store.repository import LocalStore, new_id
from backend.tools.cloudwatch import CloudWatchTool
from backend.tools.cost_explorer import CostExplorerTool
from backend.tools.trusted_advisor import TrustedAdvisorTool

log = structlog.get_logger()


class BedrockReasoner:
    """Uses Bedrock Converse API for incident reasoning; falls back to rules engine."""

    SYSTEM = """You are an expert AWS SRE and FinOps agent. Given telemetry anomalies,
produce a concise root-cause hypothesis and ranked remediation actions.
Write actions must be conservative. Prefer read-only investigation first.
Respond ONLY with valid JSON matching this schema:
{
  "title": "string",
  "summary": "string",
  "root_cause_hypothesis": "string",
  "severity": "info|warning|critical",
  "recommended_actions": [
    {
      "title": "string",
      "description": "string",
      "risk": "read|write",
      "tool_name": "string",
      "parameters": {},
      "estimated_impact": "string",
      "rollback_plan": "string"
    }
  ]
}"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        if not settings.demo_mode:
            try:
                import boto3

                self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
            except Exception as exc:  # noqa: BLE001
                log.warning("bedrock_unavailable", error=str(exc))

    def analyze(
        self,
        metric_anomalies: list[MetricAnomaly],
        cost_anomalies: list[CostAnomaly],
        ta_flags: list[dict],
        alarms: list[dict],
    ) -> dict:
        payload = {
            "metric_anomalies": [m.model_dump(mode="json") for m in metric_anomalies],
            "cost_anomalies": [c.model_dump(mode="json") for c in cost_anomalies],
            "trusted_advisor": ta_flags,
            "active_alarms": alarms,
        }
        if self._client is None:
            return self._rules_engine(metric_anomalies, cost_anomalies, ta_flags, alarms)

        prompt = f"Analyze this AWS telemetry bundle and recommend actions:\n{json.dumps(payload, default=str)}"
        try:
            resp = self._client.converse(
                modelId=self.settings.bedrock_model_id,
                system=[{"text": self.SYSTEM}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 2048, "temperature": 0.2},
            )
            text = resp["output"]["message"]["content"][0]["text"]
            start = text.find("{")
            end = text.rfind("}") + 1
            return json.loads(text[start:end])
        except Exception as exc:  # noqa: BLE001
            log.warning("bedrock_reasoning_failed", error=str(exc))
            return self._rules_engine(metric_anomalies, cost_anomalies, ta_flags, alarms)

    def _rules_engine(
        self,
        metric_anomalies: list[MetricAnomaly],
        cost_anomalies: list[CostAnomaly],
        ta_flags: list[dict],
        alarms: list[dict],
    ) -> dict:
        severity = Severity.INFO
        if any(m.severity == Severity.CRITICAL for m in metric_anomalies):
            severity = Severity.CRITICAL
        elif any(c.severity in {Severity.CRITICAL, Severity.WARNING} for c in cost_anomalies):
            severity = Severity.WARNING if severity != Severity.CRITICAL else severity

        actions: list[dict] = [
            {
                "title": "Pull 7-day metric correlation",
                "description": "Compare CPU, error rate, and latency across affected services.",
                "risk": "read",
                "tool_name": "cloudwatch_correlate",
                "parameters": {"lookback_days": 7},
                "estimated_impact": "Improves RCA confidence",
                "rollback_plan": "N/A — read-only",
            }
        ]

        ec2_cost = next((c for c in cost_anomalies if "EC2" in c.service), None)
        cpu_spike = next((m for m in metric_anomalies if m.metric_name == "CPUUtilization"), None)
        lambda_errors = next((m for m in metric_anomalies if m.metric_name == "Errors"), None)

        if cpu_spike and ec2_cost:
            actions.append(
                {
                    "title": "Scale API Auto Scaling Group +40%",
                    "description": "Increase desired capacity to absorb CPU spike and reduce error backlog.",
                    "risk": "write",
                    "tool_name": "scale_ec2_asg",
                    "parameters": {"asg_name": "prod-api-asg", "desired_capacity": 14},
                    "estimated_impact": "Stabilize p99 latency within 10 minutes",
                    "rollback_plan": "Scale back to previous desired capacity (10)",
                }
            )

        underutil = next((f for f in ta_flags if "Low Utilization" in f.get("check", "")), None)
        if underutil and underutil.get("resources", 0) > 0:
            actions.append(
                {
                    "title": "Rightsize 7 idle EC2 instances",
                    "description": "Stop instances flagged by Trusted Advisor with <10% CPU over 14 days.",
                    "risk": "write",
                    "tool_name": "rightsize_ec2",
                    "parameters": {"instance_ids": ["i-demo1", "i-demo2"], "action": "stop"},
                    "estimated_impact": f"Save ~${underutil.get('estimated_monthly_savings_usd', 0):.0f}/mo",
                    "rollback_plan": "Start instances from snapshot IDs in runbook",
                }
            )

        if lambda_errors:
            actions.append(
                {
                    "title": "Rollback checkout-webhook Lambda",
                    "description": "Point alias 'live' to previous stable version after error spike.",
                    "risk": "write",
                    "tool_name": "rollback_lambda",
                    "parameters": {"function_name": "checkout-webhook", "alias": "live"},
                    "estimated_impact": "Reduce 5xx on checkout path",
                    "rollback_plan": "Re-point alias to version noted in incident",
                }
            )

        if ec2_cost and ec2_cost.deviation_pct >= 20:
            actions.append(
                {
                    "title": "Create EC2 budget guardrail",
                    "description": "Alert when EC2 MTD spend exceeds baseline by 20%.",
                    "risk": "write",
                    "tool_name": "create_budget_alert",
                    "parameters": {
                        "account_id": "123456789012",
                        "budget": {"BudgetName": "ec2-guardrail", "BudgetLimit": {"Amount": "4500", "Unit": "USD"}},
                    },
                    "estimated_impact": "Prevent repeat cost drift",
                    "rollback_plan": "Delete budget via console",
                }
            )

        title = "Multi-signal reliability & cost drift detected"
        if lambda_errors:
            title = "Checkout path degradation with cost overrun"
        elif cpu_spike:
            title = "API cluster CPU saturation"

        summary_parts = [
            f"{len(metric_anomalies)} metric anomalies",
            f"{len(cost_anomalies)} cost anomalies",
            f"{len([a for a in alarms if a.get('state') == 'ALARM'])} active alarms",
        ]
        hypothesis = (
            "Likely combination of traffic surge on API tier (CPU spike) and unchecked "
            "instance sprawl driving EC2 cost overrun. Lambda error burst may indicate "
            "downstream dependency timeout under load."
        )
        if not metric_anomalies and cost_anomalies:
            hypothesis = "Cost drift without matching metric anomalies — investigate orphaned resources and RI coverage."

        return {
            "title": title,
            "summary": "; ".join(summary_parts),
            "root_cause_hypothesis": hypothesis,
            "severity": severity.value,
            "recommended_actions": actions,
        }


class SREAgentOrchestrator:
    """Coordinates telemetry collection, Bedrock reasoning, and incident creation."""

    def __init__(self, settings: Settings, store: LocalStore) -> None:
        self.settings = settings
        self.store = store
        self.cloudwatch = CloudWatchTool(settings)
        self.cost_explorer = CostExplorerTool(settings)
        self.trusted_advisor = TrustedAdvisorTool(settings)
        self.reasoner = BedrockReasoner(settings)

    def run_analysis(self, req: RunAnalysisRequest) -> tuple[str, IncidentReport]:
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        trace: list[AgentTraceStep] = []
        t0 = time.perf_counter()

        # Phase 1 — collect telemetry
        metric_anomalies: list[MetricAnomaly] = []
        cost_anomalies: list[CostAnomaly] = []
        ta_flags: list[dict] = []
        alarms: list[dict] = []

        if req.include_metrics:
            t1 = time.perf_counter()
            metric_anomalies = self.cloudwatch.detect_metric_anomalies(req.lookback_hours)
            alarms = self.cloudwatch.get_active_alarms()
            trace.append(
                AgentTraceStep(
                    step=1,
                    phase="collect_metrics",
                    summary=f"Found {len(metric_anomalies)} metric anomalies, {len(alarms)} alarms",
                    tool_calls=["cloudwatch.detect_metric_anomalies", "cloudwatch.get_active_alarms"],
                    duration_ms=int((time.perf_counter() - t1) * 1000),
                )
            )

        if req.include_cost:
            t2 = time.perf_counter()
            cost_anomalies = self.cost_explorer.detect_cost_anomalies()
            trace.append(
                AgentTraceStep(
                    step=2,
                    phase="collect_cost",
                    summary=f"Found {len(cost_anomalies)} cost anomalies",
                    tool_calls=["cost_explorer.detect_cost_anomalies"],
                    duration_ms=int((time.perf_counter() - t2) * 1000),
                )
            )

        if req.include_trusted_advisor:
            t3 = time.perf_counter()
            ta_flags = self.trusted_advisor.get_cost_optimization_flags()
            trace.append(
                AgentTraceStep(
                    step=3,
                    phase="trusted_advisor",
                    summary=f"Retrieved {len(ta_flags)} optimization checks",
                    tool_calls=["trusted_advisor.get_cost_optimization_flags"],
                    duration_ms=int((time.perf_counter() - t3) * 1000),
                )
            )

        # Phase 2 — Bedrock reasoning
        t4 = time.perf_counter()
        analysis = self.reasoner.analyze(metric_anomalies, cost_anomalies, ta_flags, alarms)
        trace.append(
            AgentTraceStep(
                step=4,
                phase="bedrock_reasoning",
                summary=f"Generated {len(analysis.get('recommended_actions', []))} recommended actions",
                tool_calls=["bedrock.converse"],
                duration_ms=int((time.perf_counter() - t4) * 1000),
            )
        )

        now = datetime.now(timezone.utc)
        incident_id = new_id("inc")
        actions: list[RecommendedAction] = []
        for idx, raw in enumerate(analysis.get("recommended_actions", [])):
            actions.append(
                RecommendedAction(
                    action_id=f"act_{idx+1}",
                    title=raw["title"],
                    description=raw["description"],
                    risk=ActionRisk(raw.get("risk", "read")),
                    tool_name=raw["tool_name"],
                    parameters=raw.get("parameters", {}),
                    estimated_impact=raw.get("estimated_impact", ""),
                    rollback_plan=raw.get("rollback_plan", ""),
                )
            )

        has_write = any(a.risk == ActionRisk.WRITE for a in actions)
        severity = Severity(analysis.get("severity", "warning"))

        incident = IncidentReport(
            incident_id=incident_id,
            title=analysis.get("title", "Cloud anomaly detected"),
            summary=analysis.get("summary", ""),
            status=IncidentStatus.AWAITING_APPROVAL if has_write else IncidentStatus.OPEN,
            severity=severity,
            created_at=now,
            updated_at=now,
            metric_anomalies=metric_anomalies,
            cost_anomalies=cost_anomalies,
            root_cause_hypothesis=analysis.get("root_cause_hypothesis", ""),
            recommended_actions=actions,
            agent_trace=trace,
            tags=["bedrock-agent", "auto-detected", req.scope],
        )

        trace.append(
            AgentTraceStep(
                step=5,
                phase="incident_created",
                summary=f"Incident {incident_id} created",
                tool_calls=["store.save_incident"],
                duration_ms=int((time.perf_counter() - t0) * 1000),
            )
        )
        incident.agent_trace = trace
        self.store.save_incident(incident)
        return run_id, incident
