from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import record_audit_event
from app.core.roles import require_roles
from app.core.security import encrypt_stream_key, mask_stream_key
from app.db import get_db
from app.deps import CurrentContext, get_current_context


router = APIRouter(prefix="/platform-keys", tags=["platform keys"])


def to_platform_key_out(platform_key: models.PlatformKey) -> schemas.PlatformKeyOut:
    return schemas.PlatformKeyOut(
        id=platform_key.id,
        platform=platform_key.platform,
        display_name=platform_key.display_name,
        masked_stream_key=mask_stream_key(platform_key.key_last_four),
        is_active=platform_key.is_active,
        rotated_at=platform_key.rotated_at,
        created_at=platform_key.created_at,
        updated_at=platform_key.updated_at,
    )


def get_platform_key_or_404(db: Session, key_id: str, organization_id: str) -> models.PlatformKey:
    platform_key = db.scalar(
        select(models.PlatformKey)
        .where(models.PlatformKey.id == key_id)
        .where(models.PlatformKey.organization_id == organization_id)
    )
    if platform_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform key not found")
    return platform_key


# Any authenticated org member can list keys (keys are always masked)
@router.get("", response_model=list[schemas.PlatformKeyOut])
def list_platform_keys(
    context: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    platform_keys = db.scalars(
        select(models.PlatformKey)
        .where(models.PlatformKey.organization_id == context.organization.id)
        .order_by(models.PlatformKey.platform)
    ).all()
    return [to_platform_key_out(platform_key) for platform_key in platform_keys]


# Only owner/admin can add new platform keys
@router.post("", response_model=schemas.PlatformKeyOut, status_code=status.HTTP_201_CREATED)
def create_platform_key(
    payload: schemas.PlatformKeyCreate,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
):
    platform = payload.platform.lower()
    exists = db.scalar(
        select(models.PlatformKey)
        .where(models.PlatformKey.organization_id == context.organization.id)
        .where(models.PlatformKey.platform == platform)
    )
    if exists:
        raise HTTPException(status_code=409, detail="Platform key already exists for this organization")

    platform_key = models.PlatformKey(
        organization_id=context.organization.id,
        platform=platform,
        display_name=payload.display_name,
        encrypted_stream_key=encrypt_stream_key(payload.stream_key),
        key_last_four=payload.stream_key[-4:],
    )
    db.add(platform_key)
    db.flush()
    record_audit_event(
        db,
        event_type="platform_key.created",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="platform_key",
        resource_id=platform_key.id,
        details={"platform": platform},
    )
    db.commit()
    db.refresh(platform_key)
    return to_platform_key_out(platform_key)


# Only owner/admin can update key metadata (display name, active status)
@router.patch("/{platform_key_id}", response_model=schemas.PlatformKeyOut)
def update_platform_key(
    platform_key_id: str,
    payload: schemas.PlatformKeyUpdate,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
):
    platform_key = get_platform_key_or_404(db, platform_key_id, context.organization.id)
    if payload.display_name is not None:
        platform_key.display_name = payload.display_name
    if payload.is_active is not None:
        platform_key.is_active = payload.is_active
    record_audit_event(
        db,
        event_type="platform_key.updated",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="platform_key",
        resource_id=platform_key.id,
    )
    db.commit()
    db.refresh(platform_key)
    return to_platform_key_out(platform_key)


# Only owner can permanently delete a key
@router.delete("/{platform_key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_platform_key(
    platform_key_id: str,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner")),
    db: Session = Depends(get_db),
):
    platform_key = get_platform_key_or_404(db, platform_key_id, context.organization.id)
    record_audit_event(
        db,
        event_type="platform_key.deleted",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="platform_key",
        resource_id=platform_key.id,
    )
    db.delete(platform_key)
    db.commit()


# Owner/admin can rotate keys
@router.post("/{platform_key_id}/rotate", response_model=schemas.PlatformKeyOut)
def rotate_platform_key(
    platform_key_id: str,
    payload: schemas.PlatformKeyRotate,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin")),
    db: Session = Depends(get_db),
):
    platform_key = get_platform_key_or_404(db, platform_key_id, context.organization.id)
    platform_key.encrypted_stream_key = encrypt_stream_key(payload.stream_key)
    platform_key.key_last_four = payload.stream_key[-4:]
    platform_key.rotated_at = datetime.now(UTC)
    record_audit_event(
        db,
        event_type="platform_key.rotated",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="platform_key",
        resource_id=platform_key.id,
    )
    db.commit()
    db.refresh(platform_key)
    return to_platform_key_out(platform_key)


# Owner/admin/producer can test connectivity (they need to verify before going live)
@router.post("/{platform_key_id}/test")
def test_platform_key(
    platform_key_id: str,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin", "producer")),
    db: Session = Depends(get_db),
):
    platform_key = get_platform_key_or_404(db, platform_key_id, context.organization.id)
    return {
        "platform_key_id": platform_key.id,
        "platform": platform_key.platform,
        "status": "configured" if platform_key.is_active else "inactive",
    }
