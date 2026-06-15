"""FastAPI application — Cloud SRE Agent control plane."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from backend.agent.orchestrator import SREAgentOrchestrator
from backend.config import get_settings
from backend.models.schemas import (
    ApprovalDecisionRequest,
    ApprovalRequest,
    DashboardSnapshot,
    IncidentReport,
    RunAnalysisRequest,
    RunAnalysisResponse,
)
from backend.services.approval import ApprovalService
from backend.store.repository import get_store
from backend.tools.demo_data import demo_sparklines
from backend.tools.cost_explorer import CostExplorerTool

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

settings = get_settings()
store = get_store(settings)
orchestrator = SREAgentOrchestrator(settings, store)
approval_service = ApprovalService(settings, store)
cost_tool = CostExplorerTool(settings)

app = FastAPI(
    title=settings.app_name,
    description="Autonomous Cloud Cost & Reliability Agent with Bedrock reasoning and human-in-the-loop approvals",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict:
    has_aws = bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))
    return {
        "status": "ok",
        "environment": settings.environment,
        "runtime": settings.runtime_label,
        "demo_mode": settings.demo_mode,
        "aws_configured": has_aws,
        "public_url": settings.public_base_url or None,
        "bedrock_model": settings.bedrock_model_id,
    }


@app.get("/v1/dashboard", response_model=DashboardSnapshot)
def dashboard() -> DashboardSnapshot:
    mtd, prior = cost_tool.get_mtd_spend()
    delta = ((mtd - prior) / max(prior, 1)) * 100
    incidents = store.list_incidents(limit=5)
    open_count = store.open_incident_count()
    pending = store.pending_approval_count()
    health = max(0.0, min(100.0, 100 - open_count * 12 - pending * 8))

    return DashboardSnapshot(
        generated_at=datetime.now(timezone.utc),
        health_score=round(health, 1),
        open_incidents=open_count,
        pending_approvals=pending,
        mtd_spend_usd=round(mtd, 2),
        cost_delta_pct=round(delta, 1),
        active_alarms=2 if settings.demo_mode else 0,
        services_monitored=settings.monitored_services.split(","),
        recent_incidents=incidents,
        cost_by_service=cost_tool.get_cost_by_service(),
        metric_sparklines=demo_sparklines(settings.demo_seed),
    )


@app.post("/v1/agent/analyze", response_model=RunAnalysisResponse)
def analyze(req: RunAnalysisRequest) -> RunAnalysisResponse:
    run_id, incident = orchestrator.run_analysis(req)
    approvals = approval_service.create_approval_requests(incident)
    mode = "demo" if settings.demo_mode else "live"
    return RunAnalysisResponse(run_id=run_id, incident=incident, approval_requests=approvals, mode=mode)


@app.get("/v1/incidents", response_model=list[IncidentReport])
def list_incidents() -> list[IncidentReport]:
    return store.list_incidents()


@app.get("/v1/incidents/{incident_id}", response_model=IncidentReport)
def get_incident(incident_id: str) -> IncidentReport:
    incident = store.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.get("/v1/approvals", response_model=list[ApprovalRequest])
def list_approvals() -> list[ApprovalRequest]:
    return store.list_approvals()


@app.get("/v1/approvals/{approval_id}", response_model=ApprovalRequest)
def get_approval(approval_id: str) -> ApprovalRequest:
    approval = store.get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@app.post("/v1/approvals/{approval_id}/decide", response_model=ApprovalRequest)
def decide_approval(approval_id: str, body: ApprovalDecisionRequest) -> ApprovalRequest:
    try:
        return approval_service.decide(approval_id, body)
    except KeyError:
        raise HTTPException(status_code=404, detail="Approval not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


if WEB.exists():
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB / "index.html")

    @app.get("/favicon.svg")
    def favicon() -> FileResponse:
        return FileResponse(WEB / "favicon.svg")
