import asyncio
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.routers import ws as ws_module
from app.services import stream_stats


client = TestClient(app)


LIVE_STATS = {
    "stream_id": "placeholder",
    "status": "live",
    "bitrate_kbps": 4500,
    "uptime_seconds": 120,
    "dropped_frames": 2,
    "destinations": [{"platform": "youtube", "status": "connected"}],
}


def register_org(suffix: str) -> str:
    """Register a fresh org and return an owner access token."""
    response = client.post(
        "/v1/auth/register",
        json={
            "organization_name": f"Church {suffix}",
            "organization_slug": suffix,
            "email": f"owner-{suffix}@example.com",
            "password": "super-secure-password",
            "full_name": "Owner",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def create_stream(token: str, title: str = "Sunday Service") -> str:
    response = client.post(
        "/v1/streams",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": title, "source": "screen"},
    )
    assert response.status_code == 201
    return response.json()["id"]


# ---------------------------------------------------------------------------
# stream_stats service
# ---------------------------------------------------------------------------

def test_fetch_stream_stats_success_sends_token_header(monkeypatch):
    settings = stream_stats.get_settings()
    monkeypatch.setattr(settings, "media_server_token", "test-media-token")
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Media-Server-Token")
        return httpx.Response(200, json={**LIVE_STATS, "stream_id": "abc"})

    stats = asyncio.run(
        stream_stats.fetch_stream_stats("abc", transport=httpx.MockTransport(handler))
    )
    assert seen["url"].endswith("/streams/abc/stats")
    assert seen["token"] == "test-media-token"
    assert stats["status"] == "live"
    assert stats["bitrate_kbps"] == 4500
    assert stats["destinations"] == [{"platform": "youtube", "status": "connected"}]


def test_fetch_stream_stats_falls_back_on_error_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    stats = asyncio.run(
        stream_stats.fetch_stream_stats("abc", transport=httpx.MockTransport(handler))
    )
    assert stats == stream_stats.offline_stats("abc")
    assert stats["status"] == "offline"
    assert stats["bitrate_kbps"] == 0


# ---------------------------------------------------------------------------
# GET /v1/streams/{id}/metrics
# ---------------------------------------------------------------------------

def test_metrics_endpoint_falls_back_when_media_server_down():
    # Nothing listens on the default media server URL (localhost:8001) in
    # tests, so the connection fails and the endpoint must return the
    # offline fallback instead of a 500.
    suffix = f"metrics-{uuid.uuid4().hex[:8]}"
    token = register_org(suffix)
    stream_id = create_stream(token)

    response = client.get(
        f"/v1/streams/{stream_id}/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stream_id"] == stream_id
    assert body["status"] == "offline"
    assert body["bitrate_kbps"] == 0
    assert body["viewer_count"] == 0
    assert body["uptime_seconds"] == 0
    assert body["dropped_frames"] == 0
    assert body["health_status"] == "offline"
    assert body["destinations"] == []


def test_metrics_endpoint_returns_media_server_stats(monkeypatch):
    suffix = f"metrics-live-{uuid.uuid4().hex[:8]}"
    token = register_org(suffix)
    stream_id = create_stream(token)

    async def fake_fetch(sid: str, **kwargs):
        return {**LIVE_STATS, "stream_id": sid}

    monkeypatch.setattr(stream_stats, "fetch_stream_stats", fake_fetch)

    response = client.get(
        f"/v1/streams/{stream_id}/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stream_id"] == stream_id
    assert body["status"] == "live"
    assert body["bitrate_kbps"] == 4500
    assert body["uptime_seconds"] == 120
    assert body["health_status"] == "excellent"
    assert body["destinations"] == [{"platform": "youtube", "status": "connected"}]


# ---------------------------------------------------------------------------
# Websocket /v1/ws/streams/{id}
# ---------------------------------------------------------------------------

def _connect_and_expect_close(url: str) -> int:
    with client.websocket_connect(url) as connection:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            connection.receive_json()
    return excinfo.value.code


def test_ws_rejects_missing_token():
    suffix = f"ws-noauth-{uuid.uuid4().hex[:8]}"
    token = register_org(suffix)
    stream_id = create_stream(token)

    code = _connect_and_expect_close(f"/v1/ws/streams/{stream_id}")
    assert code == 4401


def test_ws_rejects_invalid_token():
    suffix = f"ws-badtoken-{uuid.uuid4().hex[:8]}"
    token = register_org(suffix)
    stream_id = create_stream(token)

    code = _connect_and_expect_close(
        f"/v1/ws/streams/{stream_id}?token=not-a-real-jwt"
    )
    assert code == 4401


def test_ws_rejects_stream_from_another_org():
    suffix_a = f"ws-orga-{uuid.uuid4().hex[:8]}"
    suffix_b = f"ws-orgb-{uuid.uuid4().hex[:8]}"
    token_a = register_org(suffix_a)
    token_b = register_org(suffix_b)
    stream_in_org_a = create_stream(token_a)

    code = _connect_and_expect_close(
        f"/v1/ws/streams/{stream_in_org_a}?token={token_b}"
    )
    assert code == 4404


def test_ws_rejects_unknown_stream():
    suffix = f"ws-nostream-{uuid.uuid4().hex[:8]}"
    token = register_org(suffix)

    code = _connect_and_expect_close(f"/v1/ws/streams/{uuid.uuid4()}?token={token}")
    assert code == 4404


def test_ws_streams_metrics_for_authorized_user(monkeypatch):
    suffix = f"ws-live-{uuid.uuid4().hex[:8]}"
    token = register_org(suffix)
    stream_id = create_stream(token)

    calls = {"count": 0}

    async def fake_fetch(sid: str, **kwargs):
        calls["count"] += 1
        return {**LIVE_STATS, "stream_id": sid}

    # The ws handler calls stream_stats.fetch_stream_stats, so patching the
    # module attribute mocks the media-server HTTP call.
    monkeypatch.setattr(stream_stats, "fetch_stream_stats", fake_fetch)
    # Speed up the push loop so the test doesn't wait 3s between frames.
    monkeypatch.setattr(ws_module, "METRICS_PUSH_INTERVAL_SECONDS", 0.01)

    with client.websocket_connect(f"/v1/ws/streams/{stream_id}?token={token}") as connection:
        first = connection.receive_json()
        second = connection.receive_json()

    for frame in (first, second):
        assert frame["type"] == "metrics"
        assert frame["stream_id"] == stream_id
        assert frame["status"] == "live"
        assert frame["bitrate_kbps"] == 4500
        assert frame["dropped_frames"] == 2
        assert frame["health_status"] == "excellent"
        assert frame["destinations"] == [{"platform": "youtube", "status": "connected"}]
    assert calls["count"] >= 2
