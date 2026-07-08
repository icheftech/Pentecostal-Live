import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import record_audit_event
from app.core.roles import require_roles
from app.db import get_db
from app.deps import CurrentContext, get_current_context
from app.services import media_server


router = APIRouter(prefix="/streams", tags=["streams"])


def get_stream_or_404(db: Session, stream_id: str, organization_id: str) -> models.Stream:
    stream = db.scalar(
        select(models.Stream)
        .where(models.Stream.id == stream_id)
        .where(models.Stream.organization_id == organization_id)
    )
    if stream is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stream not found")
    return stream


# Any authenticated org member can view streams
@router.get("", response_model=list[schemas.StreamOut])
def list_streams(
    context: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(models.Stream)
        .where(models.Stream.organization_id == context.organization.id)
        .order_by(models.Stream.created_at.desc())
    ).all()


# Owner/admin/producer can create a stream
@router.post("", response_model=schemas.StreamOut, status_code=status.HTTP_201_CREATED)
def create_stream(
    payload: schemas.StreamCreate,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin", "producer")),
    db: Session = Depends(get_db),
):
    stream = models.Stream(
        organization_id=context.organization.id,
        title=payload.title,
        source=payload.source,
        created_by=context.user.id,
    )
    db.add(stream)
    db.flush()
    record_audit_event(
        db,
        event_type="stream.created",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="stream",
        resource_id=stream.id,
    )
    db.commit()
    db.refresh(stream)
    return stream


# Owner/admin/producer can go live
@router.post("/{stream_id}/start", response_model=schemas.StreamActionOut)
def start_stream(
    stream_id: str,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin", "producer")),
    db: Session = Depends(get_db),
):
    stream = get_stream_or_404(db, stream_id, context.organization.id)
    stream.status = "live"
    stream.started_at = datetime.now(UTC)
    stream.ended_at = None
    stream.ingest_key = secrets.token_urlsafe(24)  # fresh key per service
    record_audit_event(
        db,
        event_type="stream.started",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="stream",
        resource_id=stream.id,
    )
    db.commit()
    db.refresh(stream)
    # Media relay is best-effort: never block the state change on it.
    ingest_url, warning = media_server.start_stream_relay(db, stream)
    if warning:
        record_audit_event(
            db,
            event_type="stream.media_relay_failed",
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            resource_type="stream",
            resource_id=stream.id,
            details={"warning": warning},
        )
        db.commit()
    out = schemas.StreamActionOut.model_validate(stream)
    out.ingest_url = ingest_url
    out.warning = warning
    return out


# Owner/admin/producer can end the stream
@router.post("/{stream_id}/stop", response_model=schemas.StreamActionOut)
def stop_stream(
    stream_id: str,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin", "producer")),
    db: Session = Depends(get_db),
):
    stream = get_stream_or_404(db, stream_id, context.organization.id)
    stream.status = "ended"
    stream.ended_at = datetime.now(UTC)
    record_audit_event(
        db,
        event_type="stream.stopped",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="stream",
        resource_id=stream.id,
    )
    db.commit()
    db.refresh(stream)
    # Media relay is best-effort: never block the state change on it.
    warning = media_server.stop_stream_relay(stream)
    if warning:
        record_audit_event(
            db,
            event_type="stream.media_relay_stop_failed",
            organization_id=context.organization.id,
            actor_user_id=context.user.id,
            resource_type="stream",
            resource_id=stream.id,
            details={"warning": warning},
        )
        db.commit()
    out = schemas.StreamActionOut.model_validate(stream)
    out.warning = warning
    return out


# Owner/admin/producer can switch scenes
@router.post("/{stream_id}/scene", response_model=schemas.StreamOut)
def change_scene(
    stream_id: str,
    payload: schemas.StreamSceneRequest,
    context: CurrentContext = Depends(get_current_context),
    _: None = Depends(require_roles("owner", "admin", "producer")),
    db: Session = Depends(get_db),
):
    stream = get_stream_or_404(db, stream_id, context.organization.id)
    stream.active_scene = payload.scene
    record_audit_event(
        db,
        event_type="stream.scene_changed",
        organization_id=context.organization.id,
        actor_user_id=context.user.id,
        resource_type="stream",
        resource_id=stream.id,
        details={"scene": payload.scene},
    )
    db.commit()
    db.refresh(stream)
    return stream


# Any authenticated org member can view metrics
@router.get("/{stream_id}/metrics", response_model=schemas.StreamMetricsOut)
def get_metrics(
    stream_id: str,
    context: CurrentContext = Depends(get_current_context),
    db: Session = Depends(get_db),
):
    stream = get_stream_or_404(db, stream_id, context.organization.id)
    return schemas.StreamMetricsOut(
        stream_id=stream.id,
        bitrate_kbps=5980 if stream.status == "live" else 0,
        viewer_count=124 if stream.status == "live" else 0,
        dropped_frames=0,
        health_status="excellent" if stream.status == "live" else "offline",
    )
