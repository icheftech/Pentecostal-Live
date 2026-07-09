"""Capture Studio gateway: WebSocket in, ffmpeg RTMP publish out."""

import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import media_server.capture as capture_module
import media_server.main as main_module
from media_server.main import app, capture_manager
from pentecostal_ffmpeg import build_capture_publish_command

client = TestClient(app)


class FakeStdin:
    """Records writes; tolerates reads after close (unlike BytesIO)."""

    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self, chunk):
        self.data += chunk
        return len(chunk)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakeCapturePopen:
    """Stands in for the capture ffmpeg process; records stdin writes."""

    instances: list["FakeCapturePopen"] = []

    def __init__(self, argv, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.stdin = FakeStdin()
        self.returncode = None
        FakeCapturePopen.instances.append(self)

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


@pytest.fixture(autouse=True)
def fake_ffmpeg(monkeypatch):
    FakeCapturePopen.instances = []
    monkeypatch.setattr(capture_module.subprocess, "Popen", FakeCapturePopen)
    yield
    capture_manager.stop_all()


@pytest.fixture
def key_accepted(monkeypatch):
    async def always_valid(ingest_key, client_addr):
        return True

    monkeypatch.setattr(main_module, "validate_ingest_key", always_valid)


@pytest.fixture
def key_rejected(monkeypatch):
    async def never_valid(ingest_key, client_addr):
        return False

    monkeypatch.setattr(main_module, "validate_ingest_key", never_valid)


def wait_for(predicate, timeout=2.0):
    """Chunk writes happen on a worker thread; poll instead of racing it."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_capture_command_transcodes_webm_to_flv():
    argv = build_capture_publish_command("rtmp://ingest:1935/live/k", ffmpeg_binary="ffmpeg")
    assert argv[argv.index("-i") + 1] == "pipe:0"
    assert "libx264" in argv and "aac" in argv
    assert argv[argv.index("-f") + 1] == "flv"
    assert argv[-1] == "rtmp://ingest:1935/live/k"
    assert "-vf" not in argv


def test_capture_command_stabilize_adds_deshake():
    argv = build_capture_publish_command("rtmp://ingest:1935/live/k", stabilize=True)
    assert argv[argv.index("-vf") + 1] == "deshake"


def test_capture_stabilize_flag_reaches_ffmpeg(key_accepted):
    with client.websocket_connect("/capture/stream-4?key=good-key&stabilize=1") as ws:
        ws.receive_json()
    assert "deshake" in FakeCapturePopen.instances[0].argv


def test_capture_rejects_invalid_key(key_rejected):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/capture/stream-1?key=bogus") as ws:
            ws.receive_json()
    assert excinfo.value.code == 4403
    assert FakeCapturePopen.instances == []


def test_capture_rejects_missing_key(key_accepted):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/capture/stream-1") as ws:
            ws.receive_json()
    assert excinfo.value.code == 4403


def test_capture_pipes_chunks_into_ffmpeg(key_accepted):
    with client.websocket_connect("/capture/stream-2?key=good-key") as ws:
        assert ws.receive_json() == {"type": "capture_started", "stream_id": "stream-2"}
        ws.send_bytes(b"webm-chunk-1")
        ws.send_bytes(b"webm-chunk-2")
        assert wait_for(
            lambda: FakeCapturePopen.instances
            and bytes(FakeCapturePopen.instances[0].stdin.data) == b"webm-chunk-1webm-chunk-2"
        )

    assert len(FakeCapturePopen.instances) == 1
    process = FakeCapturePopen.instances[0]
    assert process.argv[-1] == "rtmp://localhost:1935/live/good-key"
    assert wait_for(lambda: process.stdin.closed)
    # disconnect stops the encoder
    assert capture_manager.stop("stream-2") is False


def test_capture_restart_replaces_previous_encoder(key_accepted):
    with client.websocket_connect("/capture/stream-3?key=key-a") as ws:
        ws.receive_json()
        ws.send_bytes(b"first")
        assert wait_for(
            lambda: FakeCapturePopen.instances and bytes(FakeCapturePopen.instances[0].stdin.data) == b"first"
        )
    with client.websocket_connect("/capture/stream-3?key=key-b") as ws:
        ws.receive_json()
        ws.send_bytes(b"second")
        assert wait_for(
            lambda: len(FakeCapturePopen.instances) == 2
            and bytes(FakeCapturePopen.instances[1].stdin.data) == b"second"
        )

    assert len(FakeCapturePopen.instances) == 2
