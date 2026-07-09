"""In-memory FFmpeg relay process management.

One RelayManager instance lives for the app lifetime. Each active relay is a
single FFmpeg process (built by pentecostal_ffmpeg.build_relay_command) whose
``-progress pipe:1`` output is parsed on a daemon thread to expose real
bitrate / frame-drop numbers.
"""

import logging
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pentecostal_ffmpeg import Destination, HlsSettings, build_relay_command

logger = logging.getLogger("media_server.relay")


def parse_progress_line(line: str, stats: dict) -> None:
    """Parse one ``key=value`` line of ffmpeg -progress output into stats.

    Recognised keys: bitrate (e.g. "5980.3kbits/s" or "N/A"), drop_frames,
    frame. Unknown keys and malformed values are ignored.
    """
    line = line.strip()
    if "=" not in line:
        return
    key, _, raw = line.partition("=")
    key = key.strip()
    raw = raw.strip()
    if key == "bitrate":
        value = raw.removesuffix("kbits/s").strip()
        try:
            stats["bitrate_kbps"] = int(float(value))
        except ValueError:
            pass  # "N/A" while probing
    elif key == "drop_frames":
        try:
            stats["dropped_frames"] = int(raw)
        except ValueError:
            pass
    elif key == "frame":
        try:
            stats["frame"] = int(raw)
        except ValueError:
            pass


@dataclass
class RelayHandle:
    stream_id: str
    process: subprocess.Popen
    destinations: list[Destination]
    hls: bool
    started_at_monotonic: float
    recording_file: str | None = None
    stats: dict = field(default_factory=dict)
    stats_lock: threading.Lock = field(default_factory=threading.Lock)

    def is_running(self) -> bool:
        return self.process.poll() is None


class RelayManager:
    def __init__(self, ffmpeg_binary: str, hls_root: str, recordings_root: str = "./data/recordings"):
        self._ffmpeg_binary = ffmpeg_binary
        self._hls_root = Path(hls_root)
        self._recordings_root = Path(recordings_root)
        self._relays: dict[str, RelayHandle] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        stream_id: str,
        ingest_url: str,
        destinations: list[Destination],
        hls: bool,
        record: bool = False,
    ) -> tuple[RelayHandle, bool]:
        """Start (or idempotently restart) the relay for a stream.

        Returns (handle, restarted) where restarted is True when an existing
        relay for the stream was terminated first.
        """
        restarted = self.stop(stream_id)

        hls_settings = None
        if hls:
            output_dir = self._hls_root / stream_id
            output_dir.mkdir(parents=True, exist_ok=True)
            hls_settings = HlsSettings(output_path=str(output_dir / "index.m3u8"))

        recording_file: str | None = None
        record_path: str | None = None
        if record:
            recording_dir = self._recordings_root / stream_id
            recording_dir.mkdir(parents=True, exist_ok=True)
            recording_file = datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + ".mkv"
            record_path = str(recording_dir / recording_file)

        argv = build_relay_command(
            ingest_url,
            destinations,
            hls=hls_settings,
            ffmpeg_binary=self._ffmpeg_binary,
            record_path=record_path,
        )
        logger.info("starting relay for stream %s: %d destinations, hls=%s",
                    stream_id, len(destinations), hls)
        process = subprocess.Popen(  # noqa: S603 - argv list, never a shell string
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        handle = RelayHandle(
            stream_id=stream_id,
            process=process,
            destinations=list(destinations),
            hls=hls,
            started_at_monotonic=time.monotonic(),
            recording_file=recording_file,
        )
        with self._lock:
            self._relays[stream_id] = handle

        reader = threading.Thread(
            target=self._read_progress, args=(handle,), daemon=True,
            name=f"relay-progress-{stream_id}",
        )
        reader.start()
        return handle, restarted

    def stop(self, stream_id: str) -> bool:
        """Terminate the relay for a stream. Returns True if one was running."""
        with self._lock:
            handle = self._relays.pop(stream_id, None)
        if handle is None:
            return False
        was_running = handle.is_running()
        if was_running:
            handle.process.terminate()
            try:
                handle.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("relay for stream %s did not exit; killing", stream_id)
                handle.process.kill()
                handle.process.wait(timeout=5)
        return was_running

    def stop_all(self) -> None:
        with self._lock:
            stream_ids = list(self._relays)
        for stream_id in stream_ids:
            self.stop(stream_id)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self, stream_id: str) -> dict:
        """Stats contract consumed by the main API — keep the shape stable."""
        with self._lock:
            handle = self._relays.get(stream_id)

        if handle is None or not handle.is_running():
            return {
                "stream_id": stream_id,
                "status": "offline",
                "bitrate_kbps": 0,
                "uptime_seconds": 0,
                "dropped_frames": 0,
                "destinations": [
                    {"platform": destination.platform, "status": "offline"}
                    for destination in (handle.destinations if handle else [])
                ],
            }

        with handle.stats_lock:
            snapshot = dict(handle.stats)
        return {
            "stream_id": stream_id,
            "status": "live",
            "bitrate_kbps": snapshot.get("bitrate_kbps", 0),
            "uptime_seconds": int(time.monotonic() - handle.started_at_monotonic),
            "dropped_frames": snapshot.get("dropped_frames", 0),
            "destinations": [
                {"platform": destination.platform, "status": "connected"}
                for destination in handle.destinations
            ],
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read_progress(self, handle: RelayHandle) -> None:
        stdout = handle.process.stdout
        if stdout is None:
            return
        try:
            for line in stdout:
                with handle.stats_lock:
                    parse_progress_line(line, handle.stats)
        except (ValueError, OSError):  # stream closed mid-read
            pass
