"""HTTP client for the media-server relay service (apps/media-server).

Design rule: churches must never be hard-blocked from toggling stream state
during a service. Every call here degrades gracefully — failures are returned
as a human-readable warning string instead of raising, so the API can still
flip the DB status and surface the problem to the dashboard/audit log.
"""

import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.core.config import get_settings
from app.core.security import decrypt_stream_key


logger = logging.getLogger("app.services.media_server")

REQUEST_TIMEOUT_SECONDS = 5.0

def build_ingest_url(ingest_key: str) -> str:
    """Public ingest URL producers paste into OBS/encoders."""
    settings = get_settings()
    return f"{settings.rtmp_ingest_base_url.rstrip('/')}/{ingest_key}"


def build_pull_url(ingest_key: str) -> str:
    """Ingest URL the media-server's ffmpeg pulls from (may be an internal host)."""
    settings = get_settings()
    base = settings.rtmp_pull_base_url or settings.rtmp_ingest_base_url
    return f"{base.rstrip('/')}/{ingest_key}"


def _headers() -> dict[str, str]:
    return {"X-Media-Server-Token": get_settings().media_server_token}


def _post(path: str, payload: dict | None = None) -> str | None:
    """POST to the media-server; return a warning string on any failure."""
    settings = get_settings()
    url = f"{settings.media_server_url.rstrip('/')}{path}"
    try:
        response = httpx.post(
            url,
            json=payload,
            headers=_headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("media-server returned %s for %s", exc.response.status_code, path)
        return (
            f"Media server rejected the request ({exc.response.status_code}); "
            "stream state was updated anyway."
        )
    except httpx.HTTPError as exc:
        logger.warning("media-server unreachable for %s: %s", path, exc.__class__.__name__)
        return (
            f"Media server unreachable ({exc.__class__.__name__}); "
            "stream state was updated anyway."
        )


def _active_destinations(db: Session, organization_id: str) -> list[dict]:
    """Decrypt the org's active platform keys into relay destinations.

    RTMP base URLs are resolved by the media-server from
    services/ffmpeg/pentecostal_ffmpeg/platforms.py — the single runtime
    source of truth — so only platform + key are sent. Unknown platforms are
    skipped by the media-server rather than failing the whole relay.
    """
    keys = db.scalars(
        select(models.PlatformKey)
        .where(models.PlatformKey.organization_id == organization_id)
        .where(models.PlatformKey.is_active.is_(True))
    ).all()

    return [
        {
            "platform": key.platform,
            "stream_key": decrypt_stream_key(key.encrypted_stream_key),
        }
        for key in keys
    ]


def start_stream_relay(db: Session, stream: models.Stream) -> tuple[str, str | None]:
    """Ask the media-server to start relaying `stream`.

    Returns (ingest_url, warning). warning is None on success; on any failure
    the caller should still mark the stream live and surface/audit the warning.
    """
    ingest_url = build_ingest_url(stream.ingest_key)
    destinations = _active_destinations(db, stream.organization_id)

    warning = _post(
        f"/relays/{stream.id}/start",
        {
            "ingest_url": build_pull_url(stream.ingest_key),
            "destinations": destinations,
            "hls": True,
            "record": True,
        },
    )
    return ingest_url, warning


def stop_stream_relay(stream: models.Stream) -> str | None:
    """Ask the media-server to stop relaying `stream`. Returns warning or None."""
    return _post(f"/relays/{stream.id}/stop")


def list_recordings(stream_id: str) -> list[dict]:
    """Fetch the archived recordings for a stream; empty list when unavailable."""
    settings = get_settings()
    url = f"{settings.media_server_url.rstrip('/')}/recordings/{stream_id}"
    try:
        response = httpx.get(url, headers=_headers(), timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, list) else []
    except (httpx.HTTPError, ValueError):
        logger.warning("could not list recordings for stream %s", stream_id)
        return []


def open_recording_download(stream_id: str, filename: str) -> tuple[httpx.Client, httpx.Response] | None:
    """Open a streaming download of one recording; None when unavailable.

    The caller owns closing both the response and the client (pass them to a
    StreamingResponse background task).
    """
    settings = get_settings()
    url = f"{settings.media_server_url.rstrip('/')}/recordings/{stream_id}/{filename}"
    client = httpx.Client(timeout=None)
    try:
        request = client.build_request("GET", url, headers=_headers())
        response = client.send(request, stream=True)
    except httpx.HTTPError:
        client.close()
        return None
    if response.status_code != 200:
        response.close()
        client.close()
        return None
    return client, response
