"""Standard RTMP base URLs per streaming platform.

This module is the single runtime source of truth for platform RTMP URLs.
The main API sends only platform + stream key; the media-server resolves the
URL here. packages/config/src/index.ts lists the same platforms for dashboard
display purposes only — when adding a platform, update both.
"""

PLATFORM_RTMP_URLS: dict[str, str] = {
    "youtube": "rtmp://a.rtmp.youtube.com/live2",
    "facebook": "rtmps://live-api-s.facebook.com:443/rtmp",
    "tiktok": "rtmp://push.tiktokcdn.com/live",
    "instagram": "rtmps://live-upload.instagram.com:443/rtmp",
    # Push back into our own nginx-rtmp/media-server for the church website player.
    "pmbc": "rtmp://media-server/live",
}


def resolve_rtmp_url(platform: str) -> str | None:
    """Return the standard RTMP base URL for a platform id, or None if unknown."""
    return PLATFORM_RTMP_URLS.get(platform.strip().lower())


def build_destination_url(rtmp_base_url: str, stream_key: str) -> str:
    """Join an RTMP base URL and a stream key into a full publish URL."""
    return f"{rtmp_base_url.rstrip('/')}/{stream_key}"
