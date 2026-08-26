"""Rules-engine and analysis-response tests."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.agent.orchestrator import BedrockReasoner
from backend.config import get_settings
from backend.main import app
from backend.models.schemas import CostAnomaly, MetricAnomaly, Severity

client = TestClient(app)


def test_analyze_reports_rules_engine_in_demo():
    r = client.post("/v1/agent/analyze", json={"scope": "full", "lookback_hours": 24})
    assert r.status_code == 200
    data = r.json()
    assert data["reasoner"] == "rules_engine"
    assert any(step["phase"] == "rules_engine" for step in data["incident"]["agent_trace"])
    assert not any("bedrock.converse" in (step.get("tool_calls") or []) for step in data["incident"]["agent_trace"])


def test_rules_engine_quiet_telemetry_skips_writes():
    reasoner = BedrockReasoner(get_settings())
    out = reasoner._rules_engine([], [], [], [])
    assert out["severity"] == "info"
    assert "not warranted" in out["root_cause_hypothesis"]
    assert all(action["risk"] == "read" for action in out["recommended_actions"])


def test_rules_engine_demo_signals_queue_writes():
    reasoner = BedrockReasoner(get_settings())
    metrics = [
        MetricAnomaly(
            namespace="AWS/EC2",
            metric_name="CPUUtilization",
            dimension={"InstanceId": "i-demo"},
            current_value=92.0,
            baseline_value=34.0,
            deviation_pct=170.6,
            period_start=datetime(2026, 8, 24, tzinfo=timezone.utc),
            period_end=datetime(2026, 8, 25, tzinfo=timezone.utc),
            severity=Severity.CRITICAL,
        )
    ]
    costs = [
        CostAnomaly(
            service="Amazon EC2",
            current_spend_usd=4280.0,
            baseline_spend_usd=3120.0,
            deviation_pct=37.2,
            period="MTD",
            severity=Severity.CRITICAL,
        )
    ]
    out = reasoner._rules_engine(metrics, costs, [], [])
    assert out["severity"] == "critical"
    assert any(action["risk"] == "write" for action in out["recommended_actions"])
