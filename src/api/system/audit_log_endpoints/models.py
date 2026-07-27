# ~/src/api/audit_log_endpoints/models.py
# Response models for the (read-only) audit log endpoints.

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AuditLogItem(BaseModel):
    """Shape of a single audit log entry."""

    id: int = Field(..., description="Internal numeric identifier for the audit log row.")
    action: str = Field(..., description="Machine-readable action name, e.g. 'user.create'.")
    user_id: Optional[int] = Field(default=None, description="Id of the authenticated user attributed to this action, if any.")
    api_key_id: Optional[int] = Field(default=None, description="Id of the API key attributed to this action, if any.")
    ip_address: str = Field(..., description="Client IP address the request originated from.")
    timestamp: datetime = Field(..., description="When the action was recorded.")


class AuditLogListResponse(BaseModel):
    """Response body for `GET /api/db/audit-logs`."""

    audit_logs: Optional[list[AuditLogItem]] = Field(default=None, description="Audit log entries, most recent first, present only when at least one exists.")
    message: Optional[str] = Field(default=None, description="Informational message, present only when no audit logs exist.")


class AuditLogResponse(BaseModel):
    """Response body for `GET /api/db/audit-logs/{log_id}`."""

    audit_log: AuditLogItem = Field(..., description="The requested audit log entry.")
