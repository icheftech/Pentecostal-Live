import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import models
from app.core.security import create_access_token, hash_password
from app.db import SessionLocal
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


def test_viewer_cannot_create_platform_keys():
    suffix = f"rbac-{uuid.uuid4().hex[:8]}"
    register_response = client.post(
        "/v1/auth/register",
        json={
            "organization_name": "RBAC Test Church",
            "organization_slug": suffix,
            "email": f"owner-{suffix}@example.com",
            "password": "super-secure-password",
            "full_name": "Owner",
        },
    )
    assert register_response.status_code == 201
    owner_token = register_response.json()["access_token"]

    with SessionLocal() as db:
        organization = db.scalar(
            select(models.Organization).where(models.Organization.slug == suffix)
        )
        viewer_role = db.scalar(select(models.Role).where(models.Role.name == "viewer"))
        assert organization is not None
        assert viewer_role is not None

        viewer = models.User(
            email=f"viewer-{suffix}@example.com",
            full_name="Viewer",
            password_hash=hash_password("super-secure-password"),
        )
        db.add(viewer)
        db.flush()
        db.add(
            models.Membership(
                organization_id=organization.id,
                user_id=viewer.id,
                role_id=viewer_role.id,
            )
        )
        db.commit()
        viewer_token = create_access_token(viewer.id, organization.id)

    owner_create_response = client.post(
        "/v1/platform-keys",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "platform": "facebook",
            "display_name": "Main Facebook",
            "stream_key": "abcd-efgh-ijkl-2222",
        },
    )
    assert owner_create_response.status_code == 201

    list_response = client.get(
        "/v1/platform-keys",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["masked_stream_key"] == "********2222"

    viewer_create_response = client.post(
        "/v1/platform-keys",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={
            "platform": "youtube",
            "display_name": "Viewer YouTube",
            "stream_key": "abcd-efgh-ijkl-3333",
        },
    )
    assert viewer_create_response.status_code == 403


def test_login_requires_org_selection_for_multi_org_user():
    suffix = f"multi-org-{uuid.uuid4().hex[:8]}"
    email = f"owner-{suffix}@example.com"
    password = "super-secure-password"
    first_slug = f"{suffix}-one"
    second_slug = f"{suffix}-two"

    register_response = client.post(
        "/v1/auth/register",
        json={
            "organization_name": "First Church",
            "organization_slug": first_slug,
            "email": email,
            "password": password,
            "full_name": "Owner",
        },
    )
    assert register_response.status_code == 201

    with SessionLocal() as db:
        user = db.scalar(select(models.User).where(models.User.email == email))
        owner_role = db.scalar(select(models.Role).where(models.Role.name == "owner"))
        assert user is not None
        assert owner_role is not None

        second_org = models.Organization(name="Second Church", slug=second_slug)
        db.add(second_org)
        db.flush()
        db.add(
            models.Membership(
                organization_id=second_org.id,
                user_id=user.id,
                role_id=owner_role.id,
            )
        )
        db.commit()

    login_response = client.post(
        "/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    body = login_response.json()
    assert body["access_token"] is None
    assert body["requires_org_selection"] is True
    assert {item["organization"]["slug"] for item in body["organizations"]} == {
        first_slug,
        second_slug,
    }

    selected_login_response = client.post(
        "/v1/auth/login",
        json={"email": email, "password": password, "org_slug": second_slug},
    )
    assert selected_login_response.status_code == 200
    selected_body = selected_login_response.json()
    assert selected_body["access_token"]
    assert selected_body["organization"]["slug"] == second_slug
