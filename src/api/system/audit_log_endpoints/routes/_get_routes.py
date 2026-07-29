# ~/src/api/audit_log_endpoints/routes/_get_routes.py
# Audit logs are read-only from the API: only GET routes exist here by design.

from fastapi import Depends, Query, Request

from src.api.system.audit_log_endpoints.routes.router import router

from src.api.config import SUPER_ADMIN_LEVEL
from src.services.system.monitoring import monitored
from src.api.errors import api_error
from src.api.system.audit_log_endpoints.models import AuditLogListResponse, AuditLogResponse
from src.security.validation.api_security import api_key_authorized_factory
from src.security.ip_block import with_ip_block
from src.models.crud.system.audit_log_crud import get_audit_log_by_id, get_audit_logs
from src.models.tables.system.api_key_table import ApiKey

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.get("", response_model=AuditLogListResponse, response_model_exclude_none=True)
@monitored(measuring="api", operation_type="read")
@with_ip_block
async def list_audit_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500, description="Maximum number of entries to return."),
    offset: int = Query(default=0, ge=0, description="Number of entries to skip, most-recent-first."),
    api_key: ApiKey = Depends(require_super_admin),
):
    audit_logs = await get_audit_logs(limit=limit, offset=offset)
    if not audit_logs:
        return {"message": "No audit logs found."}

    return {"audit_logs": [audit_log.to_dict() for audit_log in audit_logs]}


@router.get("/{log_id}", response_model=AuditLogResponse)
@monitored(measuring="api", operation_type="read")
@with_ip_block
async def get_audit_log(log_id: int, request: Request, api_key: ApiKey = Depends(require_super_admin)):
    audit_log = await get_audit_log_by_id(log_id)
    if audit_log is None:
        raise api_error(404, f"Audit log '{log_id}' not found.")

    return {"audit_log": audit_log.to_dict()}
