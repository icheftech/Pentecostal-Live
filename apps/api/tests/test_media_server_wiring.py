"""Start/stop wiring to the media-server, with httpx mocked out."""

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.services.media_server as media_server_service
from app import models
from app.db import SessionLocal
from app.main import app

client = TestClient(app)


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("POST", "http://media-server.test"),
                response=httpx.Response(self.status_code),
            )

    def json(self):
        return self._payload


@pytest.fixture()
def org_with_stream():
    suffix = f"media-{uuid.uuid4().hex[:8]}"
    register = client.post(
        "/v1/auth/register",
        json={
            "organization_name": "Media Test Church",
            "organization_slug": suffix,
            "email": f"producer-{suffix}@example.com",
            "password": "super-secure-password",
            "full_name": "Producer",
        },
    )
    assert register.status_code == 201
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    key = client.post(
        "/v1/platform-keys",
        headers=headers,
        json={
            "platform": "youtube",
            "display_name": "Main YouTube",
            "stream_key": "yt-secret-key-1234",
        },
    )
    assert key.status_code == 201

    stream = client.post(
        "/v1/streams",
        headers=headers,
        json={"title": "Sunday Service", "source": "screen"},
    )
    assert stream.status_code == 201
    return headers, stream.json()["id"], suffix


def test_start_calls_media_server_with_decrypted_keys(org_with_stream, monkeypatch):
    headers, stream_id, _ = org_with_stream
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        return FakeResponse(200)

    monkeypatch.setattr(media_server_service.httpx, "post", fake_post)

    response = client.post(f"/v1/streams/{stream_id}/start", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "live"
    assert body["warning"] is None
    assert body["ingest_url"].startswith("rtmp://localhost:1935/live/")

    assert len(calls) == 1
    call = calls[0]
    assert call["url"].endswith(f"/relays/{stream_id}/start")
    assert call["headers"]["X-Media-Server-Token"]
    payload = call["json"]
    assert payload["hls"] is True
    assert payload["ingest_url"] == body["ingest_url"]
    assert payload["destinations"] == [
        {
            "platform": "youtube",
            "rtmp_url": "rtmp://a.rtmp.youtube.com/live2",
            "stream_key": "yt-secret-key-1234",
        }
    ]

    # Ingest key persisted and embedded in the ingest URL
    with SessionLocal() as db:
        stream = db.get(models.Stream, stream_id)
        assert stream.ingest_key
        assert body["ingest_url"].endswith(stream.ingest_key)


def test_start_succeeds_with_warning_when_media_server_down(org_with_stream, monkeypatch):
    headers, stream_id, _ = org_with_stream

    def fake_post(url, json=None, headers=None, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(media_server_service.httpx, "post", fake_post)

    response = client.post(f"/v1/streams/{stream_id}/start", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "live"  # never hard-blocked
    assert "unreachable" in body["warning"]

    with SessionLocal() as db:
        event = db.scalar(
            select(models.AuditEvent)
            .where(models.AuditEvent.resource_id == stream_id)
            .where(models.AuditEvent.event_type == "stream.media_relay_failed")
        )
        assert event is not None
        assert "unreachable" in event.details["warning"]


def test_stop_calls_media_server(org_with_stream, monkeypatch):
    headers, stream_id, _ = org_with_stream
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(url)
        return FakeResponse(200)

    monkeypatch.setattr(media_server_service.httpx, "post", fake_post)

    client.post(f"/v1/streams/{stream_id}/start", headers=headers)
    response = client.post(f"/v1/streams/{stream_id}/stop", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ended"
    assert body["warning"] is None
    assert calls[-1].endswith(f"/relays/{stream_id}/stop")


def test_stop_succeeds_with_warning_when_media_server_down(org_with_stream, monkeypatch):
    headers, stream_id, _ = org_with_stream

    def fake_post(url, json=None, headers=None, timeout=None):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(media_server_service.httpx, "post", fake_post)

    response = client.post(f"/v1/streams/{stream_id}/stop", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ended"
    assert "unreachable" in body["warning"]

    with SessionLocal() as db:
        event = db.scalar(
            select(models.AuditEvent)
            .where(models.AuditEvent.resource_id == stream_id)
            .where(models.AuditEvent.event_type == "stream.media_relay_stop_failed")
        )
        assert event is not None


def test_start_regenerates_ingest_key_each_time(org_with_stream, monkeypatch):
    headers, stream_id, _ = org_with_stream
    monkeypatch.setattr(
        media_server_service.httpx,
        "post",
        lambda *a, **k: FakeResponse(200),
    )
    first = client.post(f"/v1/streams/{stream_id}/start", headers=headers).json()
    second = client.post(f"/v1/streams/{stream_id}/start", headers=headers).json()
    assert first["ingest_url"] != second["ingest_url"]


def test_media_server_rejection_becomes_warning(org_with_stream, monkeypatch):
    headers, stream_id, _ = org_with_stream
    monkeypatch.setattr(
        media_server_service.httpx,
        "post",
        lambda *a, **k: FakeResponse(500),
    )
    response = client.post(f"/v1/streams/{stream_id}/start", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "live"
    assert "rejected" in body["warning"]
