import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _register(suffix: str) -> dict:
    response = client.post(
        "/v1/auth/register",
        json={
            "organization_name": "Refresh Test Church",
            "organization_slug": suffix,
            "email": f"owner-{suffix}@example.com",
            "password": "super-secure-password",
            "full_name": "Owner",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_register_and_login_return_refresh_token():
    suffix = f"refresh-{uuid.uuid4().hex[:8]}"
    body = _register(suffix)
    assert body["refresh_token"]

    login_response = client.post(
        "/v1/auth/login",
        json={"email": f"owner-{suffix}@example.com", "password": "super-secure-password"},
    )
    assert login_response.status_code == 200
    login_body = login_response.json()
    assert login_body["access_token"]
    assert login_body["refresh_token"]
    assert login_body["refresh_token"] != body["refresh_token"]


def test_refresh_rotation_works_and_rotated_token_is_rejected():
    suffix = f"rotate-{uuid.uuid4().hex[:8]}"
    original_refresh = _register(suffix)["refresh_token"]

    # Rotate: old refresh token is exchanged for a new pair
    refresh_response = client.post("/v1/auth/refresh", json={"refresh_token": original_refresh})
    assert refresh_response.status_code == 200
    rotated = refresh_response.json()
    assert rotated["access_token"]
    assert rotated["refresh_token"]
    assert rotated["refresh_token"] != original_refresh

    # New access token is usable
    me_response = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {rotated['access_token']}"})
    assert me_response.status_code == 200

    # Reuse of the rotated (now revoked) token fails
    reuse_response = client.post("/v1/auth/refresh", json={"refresh_token": original_refresh})
    assert reuse_response.status_code == 401

    # The new token still works after the failed reuse
    second_rotation = client.post("/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]})
    assert second_rotation.status_code == 200


def test_logout_revokes_refresh_token():
    suffix = f"logout-{uuid.uuid4().hex[:8]}"
    refresh_token = _register(suffix)["refresh_token"]

    logout_response = client.post("/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_response.status_code == 204

    refresh_response = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 401

    # Logout is idempotent
    second_logout = client.post("/v1/auth/logout", json={"refresh_token": refresh_token})
    assert second_logout.status_code == 204


def test_garbage_refresh_token_is_rejected():
    response = client.post("/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401
