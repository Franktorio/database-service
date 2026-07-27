# ~/src/models/crud/audit_context.py
# Request-scoped context for the identity attributed to audit log writes.
#
# Populated once per request by the auth dependency chain (api_key_authorized_factory /
# cookie_authorized_factory in src/security/validation/) after a caller's credential has
# been validated, and read by audit_log_crud.audit_logged() at write time. Backed by a
# contextvars.ContextVar, so values are isolated per request/asyncio task and never leak
# across concurrent requests.

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditActor:
    """Identity attributed to audit log writes made during the current request."""

    user_id: int | None = None
    api_key_id: int | None = None
    ip_address: str = ""


_current_actor: ContextVar[AuditActor] = ContextVar("audit_actor", default=AuditActor())


def set_audit_actor(*, user_id: int | None = None, api_key_id: int | None = None, ip_address: str = "") -> None:
    """Record the identity responsible for CRUD writes made during the rest of this request."""
    _current_actor.set(AuditActor(user_id=user_id, api_key_id=api_key_id, ip_address=ip_address))


def get_audit_actor() -> AuditActor:
    """Return the identity currently attributed to audit log writes (defaults if unset)."""
    return _current_actor.get()
