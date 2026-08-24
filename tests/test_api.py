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
    assert approvals, "demo analysis should queue write actions for HITL approval"
    apr_id = approvals[0]["approval_id"]
    incident_id = r.json()["incident"]["incident_id"]

    d = client.post(f"/v1/approvals/{apr_id}/decide", json={"decision": "approved", "decided_by": "test"})
    assert d.status_code == 200
    assert d.json()["status"] in {"executed", "failed", "approved"}

    incident = client.get(f"/v1/incidents/{incident_id}").json()
    remaining = [a for a in client.get("/v1/approvals").json() if a["status"] == "pending"]
    if remaining:
        assert incident["status"] == "remediating"
    else:
        assert incident["status"] in {"resolved", "remediating"}


def test_partial_approval_does_not_resolve_incident():
    r = client.post("/v1/agent/analyze", json={})
    approvals = r.json()["approval_requests"]
    assert len(approvals) >= 2
    incident_id = r.json()["incident"]["incident_id"]

    first = client.post(
        f"/v1/approvals/{approvals[0]['approval_id']}/decide",
        json={"decision": "approved", "decided_by": "test"},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "executed"

    incident = client.get(f"/v1/incidents/{incident_id}").json()
    assert incident["status"] == "remediating"
    pending = [a for a in client.get("/v1/approvals").json() if a["status"] == "pending"]
    assert pending


def test_reject_all_dismisses_incident():
    r = client.post("/v1/agent/analyze", json={})
    approvals = r.json()["approval_requests"]
    incident_id = r.json()["incident"]["incident_id"]

    for approval in approvals:
        d = client.post(
            f"/v1/approvals/{approval['approval_id']}/decide",
            json={"decision": "rejected", "decided_by": "test"},
        )
        assert d.status_code == 200
        assert d.json()["status"] == "rejected"

    incident = client.get(f"/v1/incidents/{incident_id}").json()
    assert incident["status"] == "dismissed"
