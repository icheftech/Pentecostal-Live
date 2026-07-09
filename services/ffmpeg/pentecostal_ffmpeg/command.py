"""Pure-function builder for the FFmpeg relay command.

Given an ingest URL, a list of destination publish URLs, and optional HLS
settings, produce the exact argv list for a single FFmpeg process that fans
the ingest out to every output using the ``tee`` muxer with stream copy
(no re-encode). Nothing here touches the filesystem or spawns processes,
so it is fully unit-testable without ffmpeg installed.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Destination:
    """A single RTMP publish target (full URL including the stream key)."""

    platform: str
    url: str


@dataclass(frozen=True)
class HlsSettings:
    """HLS output settings for the local website player."""

    output_path: str  # e.g. /var/pentecostal-live/hls/<stream_id>/index.m3u8
    segment_seconds: int = 4
    playlist_size: int = 6
    delete_segments: bool = True


# Characters with special meaning inside a tee muxer output spec.
_TEE_SPECIAL = "\\|[]"


def _tee_escape(value: str) -> str:
    """Escape a URL/path for use inside a tee muxer slave spec."""
    for char in _TEE_SPECIAL:
        value = value.replace(char, f"\\{char}")
    return value


def _tee_slave_for_destination(destination: Destination) -> str:
    # onfail=ignore: one platform rejecting the push must not kill the
    # relay to the other platforms mid-service.
    return f"[f=flv:onfail=ignore]{_tee_escape(destination.url)}"


def _tee_slave_for_hls(hls: HlsSettings) -> str:
    options = [
        "f=hls",
        f"hls_time={hls.segment_seconds}",
        f"hls_list_size={hls.playlist_size}",
    ]
    if hls.delete_segments:
        options.append("hls_flags=delete_segments")
    return f"[{':'.join(options)}]{_tee_escape(hls.output_path)}"


def build_relay_command(
    ingest_url: str,
    destinations: Sequence[Destination],
    hls: HlsSettings | None = None,
    ffmpeg_binary: str = "ffmpeg",
) -> list[str]:
    """Build the full FFmpeg argv for a fan-out relay.

    - Reads the ingest (RTMP pull from nginx-rtmp).
    - Stream-copies video+audio (no transcode) into a tee muxer.
    - One tee slave per destination (flv over RTMP) plus an optional HLS slave.
    - Emits machine-readable progress on stdout (``-progress pipe:1``) so the
      media-server can parse real bitrate / frame / drop counts.

    Raises ValueError when there is nothing to output.
    """
    if not ingest_url:
        raise ValueError("ingest_url is required")
    if not destinations and hls is None:
        raise ValueError("at least one destination or an HLS output is required")

    slaves = [_tee_slave_for_destination(destination) for destination in destinations]
    if hls is not None:
        slaves.append(_tee_slave_for_hls(hls))

    return [
        ffmpeg_binary,
        "-hide_banner",
        "-loglevel", "warning",
        "-nostats",
        "-progress", "pipe:1",
        "-i", ingest_url,
        "-c", "copy",
        "-map", "0:v?",
        "-map", "0:a?",
        "-f", "tee",
        "-use_fifo", "1",
        "-fifo_options", "attempt_recovery=1:drop_pkts_on_overflow=1",
        "|".join(slaves),
    ]


def build_capture_publish_command(
    publish_url: str,
    ffmpeg_binary: str = "ffmpeg",
    video_bitrate_kbps: int = 4500,
    audio_bitrate_kbps: int = 160,
) -> list[str]:
    """Build the FFmpeg argv for the browser Capture Studio gateway.

    Reads a WebM byte stream (MediaRecorder output) from stdin, transcodes to
    H.264/AAC — platforms will not take VP8/VP9 over RTMP — and publishes to
    the ingest, where the normal relay fan-out picks it up.
    """
    if not publish_url:
        raise ValueError("publish_url is required")

    return [
        ffmpeg_binary,
        "-hide_banner",
        "-loglevel", "warning",
        "-i", "pipe:0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-g", "60",
        "-b:v", f"{video_bitrate_kbps}k",
        "-maxrate", f"{video_bitrate_kbps}k",
        "-bufsize", f"{video_bitrate_kbps * 2}k",
        "-c:a", "aac",
        "-b:a", f"{audio_bitrate_kbps}k",
        "-ar", "44100",
        "-f", "flv",
        publish_url,
    ]
