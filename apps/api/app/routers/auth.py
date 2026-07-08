from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import record_audit_event
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_db
from app.deps import CurrentContext, get_current_context
from app.token_store import issue_refresh_token


router = APIRouter(prefix="/auth", tags=["auth"])


def ensure_roles(db: Session) -> models.Role:
    roles = {
        "owner": "Full organization owner access",
        "admin": "Can manage streams, keys, users, and settings",
        "producer": "Can start streams, switch scenes, and control production",
        "viewer": "Read-only dashboard access",
    }
    owner_role: models.Role | None = None
    for name, description in roles.items():
        role = db.scalar(select(models.Role).where(models.Role.name == name))
        if role is None:
            role = models.Role(name=name, description=description)
            db.add(role)
            db.flush()
        if name == "owner":
            owner_role = role
    if owner_role is None:
        raise RuntimeError("Owner role could not be created")
    return owner_role


@router.post("/register", response_model=schemas.TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().auth_rate_limit)
def register(
    request: Request,
    payload: schemas.RegisterRequest,
    db: Session = Depends(get_db),
) -> schemas.TokenResponse:
    existing_user = db.scalar(select(models.User).where(models.User.email == payload.email.lower()))
    existing_org = db.scalar(select(models.Organization).where(models.Organization.slug == payload.organization_slug))
    if existing_user or existing_org:
        raise HTTPException(status_code=409, detail="User or organization already exists")

    owner_role = ensure_roles(db)
    organization = models.Organization(name=payload.organization_name, slug=payload.organization_slug)
    user = models.User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    db.add_all([organization, user])
    db.flush()
    db.add(models.Membership(organization_id=organization.id, user_id=user.id, role_id=owner_role.id))
    record_audit_event(
        db,
        event_type="auth.registered",
        organization_id=organization.id,
        actor_user_id=user.id,
        resource_type="organization",
        resource_id=organization.id,
    )
    refresh_token = issue_refresh_token(db, user.id, organization.id)
    db.commit()
    return schemas.TokenResponse(
        access_token=create_access_token(user.id, organization.id),
        refresh_token=refresh_token,
    )


@router.post("/login", response_model=schemas.LoginResponse)
@limiter.limit(get_settings().auth_rate_limit)
def login(request: Request, payload: schemas.LoginRequest, db: Session = Depends(get_db)) -> schemas.LoginResponse:
    # 1. Verify credentials
    user = db.scalar(select(models.User).where(models.User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    # 2. Load all org memberships for this user
    rows = db.execute(
        select(models.Organization, models.Role)
        .join(models.Membership, models.Membership.organization_id == models.Organization.id)
        .join(models.Role, models.Role.id == models.Membership.role_id)
        .where(models.Membership.user_id == user.id)
        .order_by(models.Organization.name)
    ).all()

    if not rows:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User has no organization membership")

    # 3a. org_slug provided — find that specific org
    if payload.org_slug:
        match = next(
            ((org, role) for org, role in rows if org.slug == payload.org_slug),
            None,
        )
        if match is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User is not a member of organization '{payload.org_slug}'",
            )
        org, role = match
        record_audit_event(
            db,
            event_type="auth.logged_in",
            organization_id=org.id,
            actor_user_id=user.id,
            details={"org_slug": org.slug},
        )
        refresh_token = issue_refresh_token(db, user.id, org.id)
        db.commit()
        return schemas.LoginResponse(
            access_token=create_access_token(user.id, org.id),
            refresh_token=refresh_token,
            organization=schemas.OrganizationOut.model_validate(org),
            role=role.name,
        )

    # 3b. Single org — log straight in
    if len(rows) == 1:
        org, role = rows[0]
        record_audit_event(
            db,
            event_type="auth.logged_in",
            organization_id=org.id,
            actor_user_id=user.id,
            details={"org_slug": org.slug},
        )
        refresh_token = issue_refresh_token(db, user.id, org.id)
        db.commit()
        return schemas.LoginResponse(
            access_token=create_access_token(user.id, org.id),
            refresh_token=refresh_token,
            organization=schemas.OrganizationOut.model_validate(org),
            role=role.name,
        )

    # 3c. Multiple orgs — return org list, no token yet; client must re-submit with org_slug
    return schemas.LoginResponse(
        access_token=None,
        requires_org_selection=True,
        organizations=[
            schemas.OrgMembership(
                organization=schemas.OrganizationOut.model_validate(org),
                role=role.name,
            )
            for org, role in rows
        ],
    )


@router.get("/orgs", response_model=list[schemas.OrgMembership])
def list_my_orgs(context: CurrentContext = Depends(get_current_context), db: Session = Depends(get_db)):
    """Return all orgs the authenticated user belongs to — used by the org switcher."""
    rows = db.execute(
        select(models.Organization, models.Role)
        .join(models.Membership, models.Membership.organization_id == models.Organization.id)
        .join(models.Role, models.Role.id == models.Membership.role_id)
        .where(models.Membership.user_id == context.user.id)
        .order_by(models.Organization.name)
    ).all()

    return [
        schemas.OrgMembership(
            organization=schemas.OrganizationOut.model_validate(org),
            role=role.name,
        )
        for org, role in rows
    ]


@router.post("/switch-org", response_model=schemas.LoginResponse)
def switch_org(
    payload: schemas.SwitchOrgRequest,
    context: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    """Mint a new token for a different org the user already belongs to."""
    row = db.execute(
        select(models.Organization, models.Role)
        .join(models.Membership, models.Membership.organization_id == models.Organization.id)
        .join(models.Role, models.Role.id == models.Membership.role_id)
        .where(models.Membership.user_id == context.user.id)
        .where(models.Organization.slug == payload.org_slug)
    ).first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User is not a member of organization '{payload.org_slug}'",
        )

    org, role = row
    record_audit_event(
        db,
        event_type="auth.org_switched",
        organization_id=org.id,
        actor_user_id=context.user.id,
        details={"from_org": context.organization.slug, "to_org": org.slug},
    )
    db.commit()
    return schemas.LoginResponse(
        access_token=create_access_token(context.user.id, org.id),
        organization=schemas.OrganizationOut.model_validate(org),
        role=role.name,
    )


@router.get("/me", response_model=schemas.MeResponse)
def me(context: CurrentContext = Depends(get_current_context)) -> schemas.MeResponse:
    return schemas.MeResponse(
        user=context.user,
        organization_id=context.organization.id,
        role=context.role.name,
    )
