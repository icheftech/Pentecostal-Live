"""Browser Capture Studio gateway: WebM-over-WebSocket in, RTMP publish out.

The dashboard captures a camera (webcam, or HDMI/SDI through a USB capture
device) with MediaRecorder and streams the WebM chunks over a WebSocket.
Each active capture is one FFmpeg process that reads those bytes on stdin,
transcodes to H.264/AAC, and publishes to the nginx-rtmp ingest — from there
the normal relay fan-out (platforms + HLS) takes over, exactly as if a
hardware encoder had connected.
"""

import logging
import subprocess
import threading

from pentecostal_ffmpeg import build_capture_publish_command

logger = logging.getLogger("media_server.capture")


class CaptureHandle:
    def __init__(self, stream_id: str, process: subprocess.Popen):
        self.stream_id = stream_id
        self.process = process

    def is_running(self) -> bool:
        return self.process.poll() is None

    def feed(self, chunk: bytes) -> None:
        """Write one MediaRecorder chunk to ffmpeg. Raises on a dead pipe."""
        stdin = self.process.stdin
        if stdin is None or not self.is_running():
            raise BrokenPipeError("capture encoder is not running")
        stdin.write(chunk)
        stdin.flush()


class CaptureManager:
    """One ffmpeg publish process per actively-capturing stream."""

    def __init__(self, ffmpeg_binary: str):
        self._ffmpeg_binary = ffmpeg_binary
        self._captures: dict[str, CaptureHandle] = {}
        self._lock = threading.Lock()

    def start(self, stream_id: str, publish_url: str, stabilize: bool = False) -> CaptureHandle:
        """Start (or idempotently restart) the capture encoder for a stream."""
        self.stop(stream_id)
        argv = build_capture_publish_command(
            publish_url, ffmpeg_binary=self._ffmpeg_binary, stabilize=stabilize
        )
        logger.info("starting capture encoder for stream %s", stream_id)
        process = subprocess.Popen(  # noqa: S603 - argv list, never a shell string
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        handle = CaptureHandle(stream_id=stream_id, process=process)
        with self._lock:
            self._captures[stream_id] = handle
        return handle

    def stop(self, stream_id: str) -> bool:
        """Stop the capture encoder for a stream. Returns True if one ran."""
        with self._lock:
            handle = self._captures.pop(stream_id, None)
        if handle is None:
            return False
        was_running = handle.is_running()
        stdin = handle.process.stdin
        if stdin is not None:
            try:
                stdin.close()  # EOF lets ffmpeg flush the tail of the stream
            except OSError:
                pass
        if was_running:
            try:
                handle.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("capture encoder for %s did not exit; killing", stream_id)
                handle.process.kill()
                handle.process.wait(timeout=5)
        return was_running

    def stop_all(self) -> None:
        with self._lock:
            stream_ids = list(self._captures)
        for stream_id in stream_ids:
            self.stop(stream_id)
