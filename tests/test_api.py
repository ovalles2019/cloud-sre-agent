"""Basic API tests."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dashboard():
    r = client.get("/v1/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "health_score" in data
    assert "mtd_spend_usd" in data


def test_analyze_creates_incident():
    r = client.post("/v1/agent/analyze", json={"scope": "full", "lookback_hours": 24})
    assert r.status_code == 200
    data = r.json()
    assert data["incident"]["incident_id"]
    assert len(data["incident"]["agent_trace"]) >= 4


def test_approval_flow():
    r = client.post("/v1/agent/analyze", json={})
    approvals = r.json()["approval_requests"]
    if not approvals:
        return
    apr_id = approvals[0]["approval_id"]
    d = client.post(f"/v1/approvals/{apr_id}/decide", json={"decision": "approved", "decided_by": "test"})
    assert d.status_code == 200
    assert d.json()["status"] in {"executed", "failed", "approved"}
