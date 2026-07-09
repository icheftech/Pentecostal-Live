"""Pentecostal Live FFmpeg helpers.

Pure functions for building FFmpeg relay commands plus the canonical
platform RTMP base URL constants. No subprocess management lives here —
the media-server owns process lifecycle.
"""

from pentecostal_ffmpeg.command import (
    Destination,
    HlsSettings,
    build_capture_publish_command,
    build_relay_command,
)
from pentecostal_ffmpeg.platforms import (
    PLATFORM_RTMP_URLS,
    build_destination_url,
    resolve_rtmp_url,
)

__all__ = [
    "Destination",
    "HlsSettings",
    "build_capture_publish_command",
    "build_relay_command",
    "PLATFORM_RTMP_URLS",
    "build_destination_url",
    "resolve_rtmp_url",
]
