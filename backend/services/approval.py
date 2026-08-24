"""Human-in-the-loop approval gate for write actions."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from backend.config import Settings
from backend.models.schemas import (
    ActionRisk,
    ApprovalDecisionRequest,
    ApprovalRequest,
    ApprovalStatus,
    IncidentReport,
    IncidentStatus,
)
from backend.store.repository import LocalStore, new_id
from backend.tools.remediation import RemediationTool

log = structlog.get_logger()


class ApprovalService:
    def __init__(self, settings: Settings, store: LocalStore) -> None:
        self.settings = settings
        self.store = store
        self.remediation = RemediationTool(settings)

    def create_approval_requests(self, incident: IncidentReport) -> list[ApprovalRequest]:
        if not self.settings.require_approval_for_writes:
            return []

        now = datetime.now(timezone.utc)
        created: list[ApprovalRequest] = []
        for action in incident.recommended_actions:
            if action.risk != ActionRisk.WRITE:
                continue
            approval = ApprovalRequest(
                approval_id=new_id("apr"),
                incident_id=incident.incident_id,
                action=action,
                status=ApprovalStatus.PENDING,
                requested_at=now,
            )
            self.store.save_approval(approval)
            created.append(approval)

        if created:
            incident.status = IncidentStatus.AWAITING_APPROVAL
            incident.updated_at = now
            self.store.save_incident(incident)
        return created

    def decide(self, approval_id: str, decision: ApprovalDecisionRequest) -> ApprovalRequest:
        approval = self.store.get_approval(approval_id)
        if approval is None:
            raise KeyError(f"Approval {approval_id} not found")
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval already {approval.status.value}")

        now = datetime.now(timezone.utc)
        approval.decided_at = now
        approval.decided_by = decision.decided_by
        approval.decision_note = decision.note

        if decision.decision == "rejected":
            approval.status = ApprovalStatus.REJECTED
            self.store.save_approval(approval)
            self._refresh_incident_status(approval.incident_id)
            return approval

        approval.status = ApprovalStatus.APPROVED
        self.store.save_approval(approval)

        if self.settings.require_approval_for_writes:
            result = self.remediation.execute(approval.action.tool_name, approval.action.parameters)
            approval.execution_result = result
            approval.status = ApprovalStatus.EXECUTED if result.get("ok") else ApprovalStatus.FAILED
            self.store.save_approval(approval)

        self._refresh_incident_status(approval.incident_id)
        return approval

    def _refresh_incident_status(self, incident_id: str) -> None:
        incident = self.store.get_incident(incident_id)
        if incident is None:
            return

        related = self.store.list_approvals(incident_id=incident_id)
        pending = [a for a in related if a.status == ApprovalStatus.PENDING]
        executed = [a for a in related if a.status == ApprovalStatus.EXECUTED]
        failed = [a for a in related if a.status == ApprovalStatus.FAILED]
        rejected = [a for a in related if a.status == ApprovalStatus.REJECTED]

        if pending:
            incident.status = (
                IncidentStatus.REMEDIATING if (executed or failed) else IncidentStatus.AWAITING_APPROVAL
            )
        elif failed:
            incident.status = IncidentStatus.REMEDIATING
        elif executed:
            incident.status = IncidentStatus.RESOLVED
        elif rejected:
            incident.status = IncidentStatus.DISMISSED

        incident.updated_at = datetime.now(timezone.utc)
        self.store.save_incident(incident)
