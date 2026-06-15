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
            return approval

        approval.status = ApprovalStatus.APPROVED
        self.store.save_approval(approval)

        if self.settings.require_approval_for_writes:
            result = self.remediation.execute(approval.action.tool_name, approval.action.parameters)
            approval.execution_result = result
            approval.status = ApprovalStatus.EXECUTED if result.get("ok") else ApprovalStatus.FAILED
            self.store.save_approval(approval)

            incident = self.store.get_incident(approval.incident_id)
            if incident:
                incident.status = (
                    IncidentStatus.RESOLVED if approval.status == ApprovalStatus.EXECUTED else IncidentStatus.REMEDIATING
                )
                incident.updated_at = now
                self.store.save_incident(incident)

        return approval
