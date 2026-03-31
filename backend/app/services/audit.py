from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models.audit import AuditLog
from app.db.models.security import User


def write_audit_log(
    db: Session,
    *,
    action: str,
    entity_name: str,
    entity_id: str,
    company_id: str | None = None,
    actor_user: User | None = None,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        company_id=company_id or (actor_user.company_id if actor_user else None),
        actor_user_id=actor_user.id if actor_user else None,
        action=action,
        entity_name=entity_name,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
    )
    db.add(audit_log)
    db.flush()
    return audit_log
