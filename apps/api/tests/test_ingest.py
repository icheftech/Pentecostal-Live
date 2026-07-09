"""nginx-rtmp on_publish callback: only live streams' ingest keys may publish."""

import uuid

import pytest
from fastapi.testclient import TestClient

import app.services.media_server as media_server_service
from app.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def offline_media_server(monkeypatch):
    monkeypatch.setattr(media_server_service, "_post", lambda path, payload=None: None)


def register_and_start_stream() -> tuple[str, str, str, dict]:
    """Create an org, schedule a stream, start it; return (token, ingest_key, stream_id, headers)."""
    suffix = f"ingest-{uuid.uuid4().hex[:8]}"
    register = client.post(
        "/v1/auth/register",
        json={
            "organization_name": "Ingest Test Church",
            "organization_slug": suffix,
            "email": f"owner-{suffix}@example.com",
            "password": "super-secure-password",
            "full_name": "Owner",
        },
    )
    assert register.status_code == 201
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/v1/streams", headers=headers, json={"title": "Sunday", "source": "screen"})
    assert created.status_code == 201
    stream_id = created.json()["id"]

    started = client.post(f"/v1/streams/{stream_id}/start", headers=headers)
    assert started.status_code == 200
    ingest_url = started.json()["ingest_url"]
    return token, ingest_url.rsplit("/", 1)[-1], stream_id, headers


def test_on_publish_accepts_live_ingest_key():
    _, ingest_key, _, _ = register_and_start_stream()
    response = client.post("/v1/ingest/on-publish", data={"name": ingest_key, "addr": "10.0.0.9"})
    assert response.status_code == 204


def test_on_publish_rejects_unknown_key():
    response = client.post("/v1/ingest/on-publish", data={"name": "not-a-real-key"})
    assert response.status_code == 403


def test_on_publish_rejects_missing_key():
    response = client.post("/v1/ingest/on-publish", data={})
    assert response.status_code == 403


def test_on_publish_rejects_after_stream_stops():
    _, ingest_key, stream_id, headers = register_and_start_stream()
    stopped = client.post(f"/v1/streams/{stream_id}/stop", headers=headers)
    assert stopped.status_code == 200

    response = client.post("/v1/ingest/on-publish", data={"name": ingest_key})
    assert response.status_code == 403

    # publish-done stays a no-op 204 regardless of stream state
    done = client.post("/v1/ingest/on-publish-done", data={"name": ingest_key})
    assert done.status_code == 204
