import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import record_audit_event
from app.core.roles import require_roles
from app.db import get_db
from app.deps import CurrentContext, get_current_context


router = APIRouter(prefix="/members", tags=["members"])

ASSIGNABLE_ROLES = ("owner", "admin", "producer", "viewer")
INVITATION_TTL_DAYS = 7


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes even for timezone=True columns — normalize."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def get_role_by_name_or_400(db: Session, role_name: str) -> models.Role:
    if role_name not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown role '{role_name}'. Valid roles: {', '.join(ASSIGNABLE_ROLES)}.",
        )
    role = db.scalar(select(models.Role).where(models.Role.name == role_name))
    if role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Role '{role_name}' is not configured")
    return role


def get_membership_or_404(db: Session, user_id: str, organization_id: str) -> models.Membership:
    membership = db.scalar(
        select(models.Membership)
        .where(models.Membership.user_id == user_id)
        .where(models.Membership.organization_id == organization_id)
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in this organization")
    return membership


def count_owners(db: Session, organization_id: str) -> int:
    rows = db.scalars(
        select(models.Membership.id)
        .join(models.Role, models.Role.id == models.Membership.role_id)
        .where(models.Membership.organization_id == organization_id)
        .where(models.Role.name == "owner")
    ).all()
    return len(rows)


def to_member_out(user: models.User, role: models.Role, membership: models.Membership) -> schemas.MemberOut:
    return schemas.MemberOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=role.name,
        joined_at=membership.created_at,
    )


# Any authenticated org member can list members
@router.get("", response_model=list[schemas.MemberOut])
def list_members(
    context: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(models.User, models.Role, models.Membership)
        .join(models.Membership, models.Membership.user_id == models.User.id)
        .join(models.Role, models.Role.id == models.Membership.role_id)
        .where(models.Membership.organization_id == context.organization.id)
        .order_by(models.Membership.created_at)
    ).all()
    return [to_member_out(user, role, membership) for user, role, membership in rows]


# Only owner/admin can invite members
@router.post("/invite", response_model=schemas.MemberInviteResponse, status_code=status.HTTP_201_CREATED)
def invite_member(
    payload: schemas.MemberInviteRequest,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
):
    """
    Invite a user to the organization by email.

    If a user account already exists for the email, the membership is created
    immediately. Otherwise an Invitation row is created and its one-time token
    is returned in the response. Email delivery is intentionally out of scope —
    the church admin copies the invite token/link from the dashboard and shares
    it with the invitee manually.
    """
    email = payload.email.lower()
    role = get_role_by_name_or_400(db, payload.role)

    # Only an owner may grant the owner role (mirrors the PATCH rule)
    if role.name == "owner" and context.role.name != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an owner can invite a member as owner",
        )

    existing_user = db.scalar(select(models.User).where(models.User.email == email))
    if existing_user is not None:
        existing_membership = db.scalar(
            select(models.Membership)
            .where(models.Membership.user_id == existing_user.id)
            .where(models.Membership.organization_id == context.organization.id)
        )
        if existing_membership is not None:
            raise HTTPException(status_code=409, detail="User is already a member of this organization")

        membership = models.Membership(
            organization_id=context.organization.id,
            user_id=existing_user.id,
            role_id=role.id,
        )
        db.add(membership)
        db.flush()
        record_audit_event(
            db,
            event_type="member.added",
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            resource_type="membership",
            resource_id=membership.id,
            details={"email": email, "role": role.name},
        )
        db.commit()
        return schemas.MemberInviteResponse(status="member_added", email=email, role=role.name)

    now = datetime.now(UTC)
    pending = db.scalars(
        select(models.Invitation)
        .where(models.Invitation.organization_id == context.organization.id)
        .where(models.Invitation.email == email)
        .where(models.Invitation.accepted_at.is_(None))
    ).all()
    if any(as_utc(invitation.expires_at) > now for invitation in pending):
        raise HTTPException(status_code=409, detail="An invitation for this email is already pending")

    invitation = models.Invitation(
        organization_id=context.organization.id,
        email=email,
        role_id=role.id,
        token=secrets.token_urlsafe(32),
        expires_at=now + timedelta(days=INVITATION_TTL_DAYS),
    )
    db.add(invitation)
    db.flush()
    record_audit_event(
        db,
        event_type="member.invited",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="invitation",
        resource_id=invitation.id,
        details={"email": email, "role": role.name},
    )
    db.commit()
    db.refresh(invitation)
    return schemas.MemberInviteResponse(
        status="invitation_created",
        email=email,
        role=role.name,
        invite_token=invitation.token,
        expires_at=invitation.expires_at,
    )


# Only owner/admin can change roles; owner grants/revocations are owner-only
@router.patch("/{user_id}", response_model=schemas.MemberOut)
def update_member_role(
    user_id: str,
    payload: schemas.MemberRoleUpdate,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
):
    if user_id == context.user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot change your own role")

    membership = get_membership_or_404(db, user_id, context.organization.id)
    current_role = db.get(models.Role, membership.role_id)
    new_role = get_role_by_name_or_400(db, payload.role)

    # Granting or revoking the owner role requires being an owner
    if "owner" in (new_role.name, current_role.name if current_role else None) and context.role.name != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an owner can grant or revoke the owner role",
        )

    # Demoting the last owner would leave the org without one
    if (
        current_role is not None
        and current_role.name == "owner"
        and new_role.name != "owner"
        and count_owners(db, context.organization.id) <= 1
    ):
        raise HTTPException(status_code=409, detail="Cannot demote the last owner of the organization")

    membership.role_id = new_role.id
    record_audit_event(
        db,
        event_type="member.role_changed",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="membership",
        resource_id=membership.id,
        details={
            "member_user_id": user_id,
            "old_role": current_role.name if current_role else None,
            "new_role": new_role.name,
        },
    )
    db.commit()

    user = db.get(models.User, user_id)
    if user is None:  # pragma: no cover — FK guarantees the user exists
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found in this organization")
    return to_member_out(user, new_role, membership)


# Only owner/admin can remove members; removing an owner is owner-only
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: str,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
):
    membership = get_membership_or_404(db, user_id, context.organization.id)
    member_role = db.get(models.Role, membership.role_id)

    if member_role is not None and member_role.name == "owner":
        if context.role.name != "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an owner can remove an owner",
            )
        if count_owners(db, context.organization.id) <= 1:
            raise HTTPException(status_code=409, detail="Cannot remove the last owner of the organization")

    record_audit_event(
        db,
        event_type="member.removed",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="membership",
        resource_id=membership.id,
        details={"member_user_id": user_id, "role": member_role.name if member_role else None},
    )
    db.delete(membership)
    db.commit()
