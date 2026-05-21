from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import record_audit_event
from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_db
from app.deps import CurrentContext, get_current_context


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
def register(payload: schemas.RegisterRequest, db: Session = Depends(get_db)) -> schemas.TokenResponse:
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
    db.commit()

    return schemas.TokenResponse(access_token=create_access_token(user.id, organization.id))


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)) -> schemas.TokenResponse:
    user = db.scalar(select(models.User).where(models.User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    membership = db.scalar(select(models.Membership).where(models.Membership.user_id == user.id))
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User has no organization")

    record_audit_event(
        db,
        event_type="auth.logged_in",
        organization_id=membership.organization_id,
        actor_user_id=user.id,
    )
    db.commit()
    return schemas.TokenResponse(access_token=create_access_token(user.id, membership.organization_id))


@router.get("/me", response_model=schemas.MeResponse)
def me(context: CurrentContext = Depends(get_current_context)) -> schemas.MeResponse:
    return schemas.MeResponse(
        user=context.user,
        organization_id=context.organization.id,
        role=context.role.name,
    )

