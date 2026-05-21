import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_platform_keys_are_masked():
    suffix = f"masktest-{uuid.uuid4().hex[:8]}"
    register_response = client.post(
        "/v1/auth/register",
        json={
            "organization_name": "Mask Test Church",
            "organization_slug": suffix,
            "email": f"producer-{suffix}@example.com",
            "password": "super-secure-password",
            "full_name": "Producer",
        },
    )
    assert register_response.status_code == 201
    token = register_response.json()["access_token"]

    create_response = client.post(
        "/v1/platform-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "platform": "youtube",
            "display_name": "Main YouTube",
            "stream_key": "abcd-efgh-ijkl-9999",
        },
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["masked_stream_key"] == "********9999"
    assert "abcd-efgh" not in str(body)
