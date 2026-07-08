"""Client for the media-server stats endpoint.

The media server exposes ``GET {media_server_url}/streams/{stream_id}/stats``
authenticated by the ``X-Media-Server-Token`` header and returns::

    {
        "stream_id": str,
        "status": "live" | "offline",
        "bitrate_kbps": int,
        "uptime_seconds": int,
        "dropped_frames": int,
        "destinations": [{"platform": str, "status": str}],
    }

The media server being down, slow, or returning garbage must never take the
API down with it, so every failure path collapses to an "offline" fallback.
"""

from typing import Any

import httpx

from app.core.config import get_settings


# Keep this short: these calls sit on request/websocket hot paths and the
# media server lives on the same network.
STATS_TIMEOUT_SECONDS = 2.0

# Threshold used to downgrade health when the encoder is dropping frames.
DROPPED_FRAMES_DEGRADED_THRESHOLD = 100


def offline_stats(stream_id: str) -> dict[str, Any]:
    """Fallback shape used whenever the media server can't be reached."""
    return {
        "stream_id": stream_id,
        "status": "offline",
        "bitrate_kbps": 0,
        "uptime_seconds": 0,
        "dropped_frames": 0,
        "destinations": [],
    }


async def fetch_stream_stats(
    stream_id: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Fetch live stats for a stream from the media server.

    Returns the media server's stats payload normalized onto the fallback
    shape. On any transport error, timeout, non-2xx response, or malformed
    body, returns :func:`offline_stats` instead of raising.

    ``transport`` is an injection point for tests (e.g. ``httpx.MockTransport``).
    """
    settings = get_settings()
    url = f"{settings.media_server_url.rstrip('/')}/streams/{stream_id}/stats"
    headers = {"X-Media-Server-Token": settings.media_server_token}

    fallback = offline_stats(stream_id)
    try:
        async with httpx.AsyncClient(
            timeout=STATS_TIMEOUT_SECONDS, transport=transport
        ) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        # httpx.HTTPError covers timeouts, connection errors, and 4xx/5xx via
        # raise_for_status; ValueError covers JSON decode failures.
        return fallback

    if not isinstance(data, dict):
        return fallback

    # Overlay the response onto the fallback so missing keys get safe zeros,
    # and pin stream_id to the one we asked about.
    stats = {**fallback, **data}
    stats["stream_id"] = stream_id
    if not isinstance(stats.get("destinations"), list):
        stats["destinations"] = []
    return stats


def derive_health(stats: dict[str, Any]) -> str:
    """Collapse raw stats into a coarse health label for clients."""
    if stats.get("status") != "live":
        return "offline"
    dropped = stats.get("dropped_frames") or 0
    bitrate = stats.get("bitrate_kbps") or 0
    if bitrate <= 0:
        return "degraded"
    if dropped >= DROPPED_FRAMES_DEGRADED_THRESHOLD:
        return "degraded"
    return "excellent"
