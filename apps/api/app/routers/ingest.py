"""RTMP ingest callbacks for nginx-rtmp.

nginx-rtmp's ``on_publish``/``on_publish_done`` directives POST form-encoded
fields (app, name, addr, ...) for every encoder publish attempt; ``name`` is
the per-stream ingest key minted by ``POST /v1/streams/{id}/start``. A 2xx
response allows the publish; anything else rejects it.

These endpoints are called by nginx, not browsers, so they carry no JWT.
Expose them to the ingest host's network only. They reveal nothing about the
stream and mutate nothing — validation just keeps unauthorized encoders off
the RTMP port.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.audit import record_audit_event
from app.db import get_db


router = APIRouter(prefix="/ingest", tags=["ingest"])


def find_live_stream_by_ingest_key(db: Session, ingest_key: str) -> models.Stream | None:
    if not ingest_key:
        return None
    return db.scalar(
        select(models.Stream)
        .where(models.Stream.ingest_key == ingest_key)
        .where(models.Stream.status == "live")
    )


@router.post("/on-publish", status_code=status.HTTP_204_NO_CONTENT)
def on_publish(
    name: str = Form(""),
    addr: str = Form(""),
    db: Session = Depends(get_db),
) -> None:
    stream = find_live_stream_by_ingest_key(db, name)
    if stream is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unknown or inactive ingest key",
        )
    record_audit_event(
        db,
        event_type="ingest.publish_accepted",
        organization_id=stream.organization_id,
        actor_user_id=None,
        resource_type="stream",
        resource_id=stream.id,
        details={"encoder_addr": addr},
    )
    db.commit()


@router.post("/on-publish-done", status_code=status.HTTP_204_NO_CONTENT)
def on_publish_done(
    name: str = Form(""),
    addr: str = Form(""),
    db: Session = Depends(get_db),
) -> None:
    # Informational only — the encoder disconnected. Never reject.
    stream = db.scalar(select(models.Stream).where(models.Stream.ingest_key == name)) if name else None
    if stream is not None:
        record_audit_event(
            db,
            event_type="ingest.publish_stopped",
            organization_id=stream.organization_id,
            actor_user_id=None,
            resource_type="stream",
            resource_id=stream.id,
            details={"encoder_addr": addr},
        )
        db.commit()
