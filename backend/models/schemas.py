"""Pydantic schemas for API and agent payloads."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    AWAITING_APPROVAL = "awaiting_approval"
    REMEDIATING = "remediating"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    FAILED = "failed"


class ActionRisk(str, Enum):
    READ = "read"
    WRITE = "write"


class MetricAnomaly(BaseModel):
    namespace: str
    metric_name: str
    dimension: dict[str, str] = Field(default_factory=dict)
    current_value: float
    baseline_value: float
    deviation_pct: float
    period_start: datetime
    period_end: datetime
    severity: Severity


class CostAnomaly(BaseModel):
    service: str
    current_spend_usd: float
    baseline_spend_usd: float
    deviation_pct: float
    period: str
    severity: Severity


class RecommendedAction(BaseModel):
    action_id: str
    title: str
    description: str
    risk: ActionRisk
    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    estimated_impact: str = ""
    rollback_plan: str = ""


class AgentTraceStep(BaseModel):
    step: int
    phase: str
    summary: str
    tool_calls: list[str] = Field(default_factory=list)
    duration_ms: int = 0


class IncidentReport(BaseModel):
    incident_id: str
    title: str
    summary: str
    status: IncidentStatus
    severity: Severity
    created_at: datetime
    updated_at: datetime
    metric_anomalies: list[MetricAnomaly] = Field(default_factory=list)
    cost_anomalies: list[CostAnomaly] = Field(default_factory=list)
    root_cause_hypothesis: str = ""
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    approval_id: str
    incident_id: str
    action: RecommendedAction
    status: ApprovalStatus
    requested_at: datetime
    decided_at: datetime | None = None
    decided_by: str | None = None
    decision_note: str = ""
    execution_result: dict[str, Any] | None = None


class RunAnalysisRequest(BaseModel):
    scope: str = "full"
    lookback_hours: int = 24
    include_cost: bool = True
    include_metrics: bool = True
    include_trusted_advisor: bool = True


class RunAnalysisResponse(BaseModel):
    run_id: str
    incident: IncidentReport
    approval_requests: list[ApprovalRequest] = Field(default_factory=list)
    mode: str


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = ""
    decided_by: str = "operator"


class DashboardSnapshot(BaseModel):
    generated_at: datetime
    health_score: float
    open_incidents: int
    pending_approvals: int
    mtd_spend_usd: float
    cost_delta_pct: float
    active_alarms: int
    services_monitored: list[str]
    recent_incidents: list[IncidentReport]
    cost_by_service: dict[str, float]
    metric_sparklines: dict[str, list[float]]
