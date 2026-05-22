from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.audit import record_audit_event
from app.core.roles import require_roles
from app.db import get_db
from app.deps import CurrentContext, get_current_context


router = APIRouter(prefix="/organizations", tags=["organizations"])


# Any authenticated org member can view the org
@router.get("/current", response_model=schemas.OrganizationOut)
def get_current_organization(context: CurrentContext = Depends(get_current_context)):
    return context.organization


# Only owner/admin can update org details
@router.patch("/current", response_model=schemas.OrganizationOut)
def update_current_organization(
    payload: schemas.OrganizationUpdate,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
):
    if payload.name is not None:
        context.organization.name = payload.name
    record_audit_event(
        db,
        event_type="organization.updated",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="organization",
        resource_id=context.organization.id,
    )
    db.commit()
    db.refresh(context.organization)
    return context.organization
