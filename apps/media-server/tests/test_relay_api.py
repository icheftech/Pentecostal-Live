import io
import time

import pytest
from fastapi.testclient import TestClient

import media_server.relay as relay_module
from media_server.main import app, relay_manager
from media_server.relay import parse_progress_line

AUTH = {"X-Media-Server-Token": "test-media-token"}

client = TestClient(app)


PROGRESS_OUTPUT = (
    "frame=300\n"
    "fps=30.0\n"
    "bitrate=4501.6kbits/s\n"
    "total_size=1234567\n"
    "out_time=00:00:10.000000\n"
    "dup_frames=0\n"
    "drop_frames=7\n"
    "speed=1.0x\n"
    "progress=continue\n"
)


class FakePopen:
    """Stands in for the ffmpeg process; emits canned -progress output."""

    instances: list["FakePopen"] = []

    def __init__(self, argv, **kwargs):
        self.argv = argv
        self.kwargs = kwargs
        self.stdout = io.StringIO(PROGRESS_OUTPUT)
        self.returncode = None
        self.terminated = False
        FakePopen.instances.append(self)

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


@pytest.fixture(autouse=True)
def fake_ffmpeg(monkeypatch):
    FakePopen.instances = []
    monkeypatch.setattr(relay_module.subprocess, "Popen", FakePopen)
    yield
    relay_manager.stop_all()


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_endpoints_reject_missing_token():
    assert client.post("/relays/s1/start", json={"ingest_url": "rtmp://x/live/k"}).status_code == 401
    assert client.post("/relays/s1/stop").status_code == 401
    assert client.get("/streams/s1/stats").status_code == 401


def test_endpoints_reject_wrong_token():
    response = client.post(
        "/relays/s1/stop", headers={"X-Media-Server-Token": "wrong"}
    )
    assert response.status_code == 401


def test_health_is_public():
    assert client.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

def test_start_spawns_ffmpeg_with_expected_command():
    response = client.post(
        "/relays/stream-1/start",
        headers=AUTH,
        json={
            "ingest_url": "rtmp://localhost:1935/live/ingest-key",
            "destinations": [
                {"platform": "youtube", "rtmp_url": "rtmp://a.rtmp.youtube.com/live2", "stream_key": "yt-key"},
                {"platform": "facebook", "rtmp_url": "rtmps://live-api-s.facebook.com:443/rtmp", "stream_key": "fb-key"},
            ],
            "hls": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stream_id"] == "stream-1"
    assert body["status"] == "live"
    assert body["restarted"] is False
    assert [d["platform"] for d in body["destinations"]] == ["youtube", "facebook"]

    assert len(FakePopen.instances) == 1
    argv = FakePopen.instances[0].argv
    assert argv[argv.index("-i") + 1] == "rtmp://localhost:1935/live/ingest-key"
    tee = argv[-1]
    assert "rtmp://a.rtmp.youtube.com/live2/yt-key" in tee
    assert "rtmps://live-api-s.facebook.com:443/rtmp/fb-key" in tee
    assert "f=hls" in tee and "stream-1/index.m3u8" in tee


def test_start_resolves_rtmp_url_from_platform_when_omitted():
    response = client.post(
        "/relays/stream-2/start",
        headers=AUTH,
        json={
            "ingest_url": "rtmp://localhost:1935/live/k",
            "destinations": [{"platform": "youtube", "stream_key": "yt-key"}],
            "hls": False,
        },
    )
    assert response.status_code == 200
    assert "rtmp://a.rtmp.youtube.com/live2/yt-key" in FakePopen.instances[0].argv[-1]


def test_start_unknown_platform_is_skipped_not_fatal():
    response = client.post(
        "/relays/stream-3/start",
        headers=AUTH,
        json={
            "ingest_url": "rtmp://localhost:1935/live/k",
            "destinations": [
                {"platform": "twitch", "stream_key": "tw-key"},
                {"platform": "youtube", "stream_key": "yt-key"},
            ],
        },
    )
    assert response.status_code == 200
    statuses = {d["platform"]: d["status"] for d in response.json()["destinations"]}
    assert statuses == {"youtube": "connected", "twitch": "skipped_unknown_platform"}
    # only the resolvable destination reaches ffmpeg
    tee = FakePopen.instances[0].argv[-1]
    assert "yt-key" in tee and "tw-key" not in tee


def test_start_all_unknown_and_no_hls_is_422():
    response = client.post(
        "/relays/stream-3b/start",
        headers=AUTH,
        json={
            "ingest_url": "rtmp://localhost:1935/live/k",
            "destinations": [{"platform": "twitch", "stream_key": "tw-key"}],
            "hls": False,
        },
    )
    assert response.status_code == 422


def test_start_with_no_outputs_is_422():
    response = client.post(
        "/relays/stream-4/start",
        headers=AUTH,
        json={"ingest_url": "rtmp://localhost:1935/live/k", "destinations": [], "hls": False},
    )
    assert response.status_code == 422


def test_start_twice_restarts_existing_relay():
    payload = {
        "ingest_url": "rtmp://localhost:1935/live/k",
        "destinations": [{"platform": "youtube", "stream_key": "yt"}],
        "hls": False,
    }
    first = client.post("/relays/stream-5/start", headers=AUTH, json=payload)
    second = client.post("/relays/stream-5/start", headers=AUTH, json=payload)
    assert first.json()["restarted"] is False
    assert second.json()["restarted"] is True
    assert FakePopen.instances[0].terminated is True
    assert len(FakePopen.instances) == 2


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def test_stats_reflect_parsed_ffmpeg_progress():
    client.post(
        "/relays/stream-6/start",
        headers=AUTH,
        json={
            "ingest_url": "rtmp://localhost:1935/live/k",
            "destinations": [{"platform": "youtube", "stream_key": "yt"}],
            "hls": True,
        },
    )
    # progress reader thread consumes the canned output
    assert wait_for(
        lambda: client.get("/streams/stream-6/stats", headers=AUTH).json()["bitrate_kbps"] == 4501
    )
    stats = client.get("/streams/stream-6/stats", headers=AUTH).json()
    assert stats == {
        "stream_id": "stream-6",
        "status": "live",
        "bitrate_kbps": 4501,
        "uptime_seconds": stats["uptime_seconds"],  # non-deterministic, checked below
        "dropped_frames": 7,
        "destinations": [{"platform": "youtube", "status": "connected"}],
    }
    assert stats["uptime_seconds"] >= 0


def test_stats_offline_when_no_relay():
    response = client.get("/streams/never-started/stats", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {
        "stream_id": "never-started",
        "status": "offline",
        "bitrate_kbps": 0,
        "uptime_seconds": 0,
        "dropped_frames": 0,
        "destinations": [],
    }


def test_stats_offline_when_process_died():
    client.post(
        "/relays/stream-7/start",
        headers=AUTH,
        json={
            "ingest_url": "rtmp://localhost:1935/live/k",
            "destinations": [{"platform": "youtube", "stream_key": "yt"}],
            "hls": False,
        },
    )
    FakePopen.instances[0].returncode = 1  # simulate ffmpeg crash
    stats = client.get("/streams/stream-7/stats", headers=AUTH).json()
    assert stats["status"] == "offline"
    assert stats["bitrate_kbps"] == 0
    assert stats["destinations"] == [{"platform": "youtube", "status": "offline"}]


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------

def test_stop_terminates_process():
    client.post(
        "/relays/stream-8/start",
        headers=AUTH,
        json={
            "ingest_url": "rtmp://localhost:1935/live/k",
            "destinations": [{"platform": "youtube", "stream_key": "yt"}],
            "hls": False,
        },
    )
    response = client.post("/relays/stream-8/stop", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"stream_id": "stream-8", "status": "offline", "was_running": True}
    assert FakePopen.instances[0].terminated is True

    stats = client.get("/streams/stream-8/stats", headers=AUTH).json()
    assert stats["status"] == "offline"


def test_stop_is_idempotent_when_not_running():
    response = client.post("/relays/nothing-here/stop", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["was_running"] is False


# ---------------------------------------------------------------------------
# Progress parsing unit tests
# ---------------------------------------------------------------------------

def test_parse_progress_line_bitrate_and_drops():
    stats: dict = {}
    parse_progress_line("bitrate=5980.3kbits/s\n", stats)
    parse_progress_line("drop_frames=12\n", stats)
    parse_progress_line("frame=100\n", stats)
    assert stats == {"bitrate_kbps": 5980, "dropped_frames": 12, "frame": 100}


def test_parse_progress_line_handles_na_and_garbage():
    stats: dict = {}
    parse_progress_line("bitrate=N/A\n", stats)
    parse_progress_line("drop_frames=oops\n", stats)
    parse_progress_line("not a key value line\n", stats)
    parse_progress_line("", stats)
    assert stats == {}
