"""In-memory / DynamoDB persistence for incidents and approvals."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.config import Settings, get_settings
from backend.models.schemas import (
    ApprovalRequest,
    ApprovalStatus,
    IncidentReport,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LocalStore:
    """In-memory store for local demo and tests."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._incidents: dict[str, IncidentReport] = {}
        self._approvals: dict[str, ApprovalRequest] = {}

    def save_incident(self, incident: IncidentReport) -> IncidentReport:
        self._incidents[incident.incident_id] = incident
        return incident

    def get_incident(self, incident_id: str) -> IncidentReport | None:
        return self._incidents.get(incident_id)

    def list_incidents(self, limit: int = 50) -> list[IncidentReport]:
        items = sorted(self._incidents.values(), key=lambda i: i.created_at, reverse=True)
        return items[:limit]

    def save_approval(self, approval: ApprovalRequest) -> ApprovalRequest:
        self._approvals[approval.approval_id] = approval
        return approval

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        return self._approvals.get(approval_id)

    def list_approvals(
        self,
        status: ApprovalStatus | None = None,
        incident_id: str | None = None,
    ) -> list[ApprovalRequest]:
        items = list(self._approvals.values())
        if incident_id:
            items = [a for a in items if a.incident_id == incident_id]
        if status:
            items = [a for a in items if a.status == status]
        return sorted(items, key=lambda a: a.requested_at, reverse=True)

    def clear(self) -> None:
        self._incidents.clear()
        self._approvals.clear()

    def open_incident_count(self) -> int:
        from backend.models.schemas import IncidentStatus

        open_statuses = {
            IncidentStatus.OPEN,
            IncidentStatus.INVESTIGATING,
            IncidentStatus.AWAITING_APPROVAL,
            IncidentStatus.REMEDIATING,
        }
        return sum(1 for i in self._incidents.values() if i.status in open_statuses)

    def pending_approval_count(self) -> int:
        return sum(1 for a in self._approvals.values() if a.status == ApprovalStatus.PENDING)


class DynamoStore(LocalStore):
    """DynamoDB-backed store for deployed environments."""

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(settings)
        import boto3

        self._ddb = boto3.resource("dynamodb", region_name=self.settings.aws_region)
        self._incidents_table = self._ddb.Table(self.settings.dynamodb_incidents_table)
        self._approvals_table = self._ddb.Table(self.settings.dynamodb_approvals_table)

    @staticmethod
    def _serialize(model: Any) -> dict[str, Any]:
        return json.loads(model.model_dump_json())

    def save_incident(self, incident: IncidentReport) -> IncidentReport:
        self._incidents_table.put_item(Item=self._serialize(incident))
        self._incidents[incident.incident_id] = incident
        return incident

    def save_approval(self, approval: ApprovalRequest) -> ApprovalRequest:
        self._approvals_table.put_item(Item=self._serialize(approval))
        self._approvals[approval.approval_id] = approval
        return approval

    def get_incident(self, incident_id: str) -> IncidentReport | None:
        item = self._incidents_table.get_item(Key={"incident_id": incident_id}).get("Item")
        if not item:
            return None
        incident = IncidentReport.model_validate(item)
        self._incidents[incident_id] = incident
        return incident

    def list_incidents(self, limit: int = 50) -> list[IncidentReport]:
        items = [
            IncidentReport.model_validate(item)
            for item in self._incidents_table.scan().get("Items", [])
        ]
        items.sort(key=lambda i: i.created_at, reverse=True)
        return items[:limit]

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        item = self._approvals_table.get_item(Key={"approval_id": approval_id}).get("Item")
        if not item:
            return None
        approval = ApprovalRequest.model_validate(item)
        self._approvals[approval_id] = approval
        return approval

    def list_approvals(
        self,
        status: ApprovalStatus | None = None,
        incident_id: str | None = None,
    ) -> list[ApprovalRequest]:
        items = [
            ApprovalRequest.model_validate(item)
            for item in self._approvals_table.scan().get("Items", [])
        ]
        if incident_id:
            items = [a for a in items if a.incident_id == incident_id]
        if status:
            items = [a for a in items if a.status == status]
        return sorted(items, key=lambda a: a.requested_at, reverse=True)

    def open_incident_count(self) -> int:
        from backend.models.schemas import IncidentStatus

        open_statuses = {
            IncidentStatus.OPEN,
            IncidentStatus.INVESTIGATING,
            IncidentStatus.AWAITING_APPROVAL,
            IncidentStatus.REMEDIATING,
        }
        return sum(1 for i in self.list_incidents(limit=200) if i.status in open_statuses)

    def pending_approval_count(self) -> int:
        return sum(1 for a in self.list_approvals(status=ApprovalStatus.PENDING))


def get_store(settings: Settings | None = None) -> LocalStore:
    settings = settings or get_settings()
    if settings.use_local_store:
        return LocalStore(settings)
    return DynamoStore(settings)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
