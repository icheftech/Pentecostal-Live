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

# Standard RTMP base URLs per platform. Mirrors packages/config/src/index.ts
# and services/ffmpeg/pentecostal_ffmpeg/platforms.py — keep the three in sync.
PLATFORM_RTMP_URLS: dict[str, str] = {
    "youtube": "rtmp://a.rtmp.youtube.com/live2",
    "facebook": "rtmps://live-api-s.facebook.com:443/rtmp",
    "tiktok": "rtmp://push.tiktokcdn.com/live",
    "instagram": "rtmps://live-upload.instagram.com:443/rtmp",
    "pmbc": "rtmp://media-server/live",
}


def build_ingest_url(ingest_key: str) -> str:
    settings = get_settings()
    return f"{settings.rtmp_ingest_base_url.rstrip('/')}/{ingest_key}"


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


def _active_destinations(db: Session, organization_id: str) -> tuple[list[dict], list[str]]:
    """Decrypt the org's active platform keys into relay destinations.

    Returns (destinations, skipped_platforms). Platforms without a known RTMP
    base URL are skipped rather than failing the whole relay.
    """
    keys = db.scalars(
        select(models.PlatformKey)
        .where(models.PlatformKey.organization_id == organization_id)
        .where(models.PlatformKey.is_active.is_(True))
    ).all()

    destinations: list[dict] = []
    skipped: list[str] = []
    for key in keys:
        rtmp_url = PLATFORM_RTMP_URLS.get(key.platform)
        if rtmp_url is None:
            skipped.append(key.platform)
            continue
        destinations.append(
            {
                "platform": key.platform,
                "rtmp_url": rtmp_url,
                "stream_key": decrypt_stream_key(key.encrypted_stream_key),
            }
        )
    return destinations, skipped


def start_stream_relay(db: Session, stream: models.Stream) -> tuple[str, str | None]:
    """Ask the media-server to start relaying `stream`.

    Returns (ingest_url, warning). warning is None on success; on any failure
    the caller should still mark the stream live and surface/audit the warning.
    """
    ingest_url = build_ingest_url(stream.ingest_key)
    destinations, skipped = _active_destinations(db, stream.organization_id)

    warning = _post(
        f"/relays/{stream.id}/start",
        {
            "ingest_url": ingest_url,
            "destinations": destinations,
            "hls": True,
        },
    )
    if warning is None and skipped:
        warning = (
            "Relay started, but platforms without a known RTMP URL were skipped: "
            + ", ".join(sorted(skipped))
        )
    return ingest_url, warning


def stop_stream_relay(stream: models.Stream) -> str | None:
    """Ask the media-server to stop relaying `stream`. Returns warning or None."""
    return _post(f"/relays/{stream.id}/stop")
