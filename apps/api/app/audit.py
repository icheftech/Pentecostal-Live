from sqlalchemy.orm import Session

from app import models


def record_audit_event(
    db: Session,
    *,
    event_type: str,
    organization_id: str | None,
    actor_user_id: str | None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        models.AuditEvent(
            event_type=event_type,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
    )

