import uuid

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)

PASSWORD = "super-secure-password"


def register_org(prefix: str) -> tuple[str, str, str]:
    """Register a fresh org. Returns (owner_token, org_slug, owner_email)."""
    suffix = f"{prefix}-{uuid.uuid4().hex[:8]}"
    email = f"owner-{suffix}@example.com"
    response = client.post(
        "/v1/auth/register",
        json={
            "organization_name": f"Church {suffix}",
            "organization_slug": suffix,
            "email": email,
            "password": PASSWORD,
            "full_name": "Owner",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"], suffix, email


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def invite_and_accept(owner_token: str, email: str, role: str) -> str:
    """Invite a brand-new user and redeem the invitation. Returns their token."""
    invite_response = client.post(
        "/v1/members/invite",
        headers=auth(owner_token),
        json={"email": email, "role": role},
    )
    assert invite_response.status_code == 201, invite_response.text
    body = invite_response.json()
    assert body["status"] == "invitation_created"
    accept_response = client.post(
        "/v1/auth/accept-invite",
        json={"token": body["invite_token"], "password": PASSWORD, "full_name": "Invited Member"},
    )
    assert accept_response.status_code == 201, accept_response.text
    return accept_response.json()["access_token"]


def get_user_id(token: str) -> str:
    response = client.get("/v1/auth/me", headers=auth(token))
    assert response.status_code == 200
    return response.json()["user"]["id"]


def test_invite_and_accept_flow():
    owner_token, slug, owner_email = register_org("invite-flow")
    invitee_email = f"producer-{slug}@example.com"

    invite_response = client.post(
        "/v1/members/invite",
        headers=auth(owner_token),
        json={"email": invitee_email, "role": "producer"},
    )
    assert invite_response.status_code == 201
    invite_body = invite_response.json()
    assert invite_body["status"] == "invitation_created"
    assert invite_body["invite_token"]
    assert invite_body["role"] == "producer"

    # A second invite for the same email is rejected while one is pending
    duplicate_response = client.post(
        "/v1/members/invite",
        headers=auth(owner_token),
        json={"email": invitee_email, "role": "viewer"},
    )
    assert duplicate_response.status_code == 409

    accept_response = client.post(
        "/v1/auth/accept-invite",
        json={"token": invite_body["invite_token"], "password": PASSWORD, "full_name": "New Producer"},
    )
    assert accept_response.status_code == 201
    member_token = accept_response.json()["access_token"]

    me_response = client.get("/v1/auth/me", headers=auth(member_token))
    assert me_response.status_code == 200
    assert me_response.json()["role"] == "producer"

    members_response = client.get("/v1/members", headers=auth(owner_token))
    assert members_response.status_code == 200
    members = members_response.json()
    assert {member["email"] for member in members} == {owner_email, invitee_email}
    assert {member["role"] for member in members} == {"owner", "producer"}

    # The token is single-use
    reuse_response = client.post(
        "/v1/auth/accept-invite",
        json={"token": invite_body["invite_token"], "password": PASSWORD, "full_name": "Imposter"},
    )
    assert reuse_response.status_code == 400


def test_accept_invite_rejects_unknown_token():
    response = client.post(
        "/v1/auth/accept-invite",
        json={"token": "not-a-real-token-at-all", "password": PASSWORD, "full_name": "Nobody"},
    )
    assert response.status_code == 400


def test_invite_existing_user_creates_membership_directly():
    owner_token, slug, _ = register_org("invite-existing")
    other_owner_token, other_slug, other_email = register_org("invite-existing-other")

    invite_response = client.post(
        "/v1/members/invite",
        headers=auth(owner_token),
        json={"email": other_email, "role": "viewer"},
    )
    assert invite_response.status_code == 201
    body = invite_response.json()
    assert body["status"] == "member_added"
    assert body["invite_token"] is None

    # The existing user can now log into the inviting org
    login_response = client.post(
        "/v1/auth/login",
        json={"email": other_email, "password": PASSWORD, "org_slug": slug},
    )
    assert login_response.status_code == 200
    assert login_response.json()["role"] == "viewer"

    # Inviting them again is a conflict
    repeat_response = client.post(
        "/v1/members/invite",
        headers=auth(owner_token),
        json={"email": other_email, "role": "viewer"},
    )
    assert repeat_response.status_code == 409


def test_member_endpoints_rbac():
    owner_token, slug, _ = register_org("member-rbac")
    viewer_token = invite_and_accept(owner_token, f"viewer-{slug}@example.com", "viewer")
    owner_id = get_user_id(owner_token)

    # Any member can list
    list_response = client.get("/v1/members", headers=auth(viewer_token))
    assert list_response.status_code == 200
    assert len(list_response.json()) == 2

    # Viewers cannot invite, change roles, or remove members
    invite_response = client.post(
        "/v1/members/invite",
        headers=auth(viewer_token),
        json={"email": f"sneaky-{slug}@example.com", "role": "viewer"},
    )
    assert invite_response.status_code == 403

    patch_response = client.patch(
        f"/v1/members/{owner_id}",
        headers=auth(viewer_token),
        json={"role": "viewer"},
    )
    assert patch_response.status_code == 403

    delete_response = client.delete(f"/v1/members/{owner_id}", headers=auth(viewer_token))
    assert delete_response.status_code == 403

    # Unauthenticated requests are rejected
    assert client.get("/v1/members").status_code == 401


def test_owner_role_changes_require_owner():
    owner_token, slug, _ = register_org("owner-gate")
    admin_token = invite_and_accept(owner_token, f"admin-{slug}@example.com", "admin")
    producer_token = invite_and_accept(owner_token, f"producer-{slug}@example.com", "producer")
    owner_id = get_user_id(owner_token)
    admin_id = get_user_id(admin_token)
    producer_id = get_user_id(producer_token)

    # Admin can manage non-owner roles
    demote_response = client.patch(
        f"/v1/members/{producer_id}",
        headers=auth(admin_token),
        json={"role": "viewer"},
    )
    assert demote_response.status_code == 200
    assert demote_response.json()["role"] == "viewer"

    # Admin cannot grant owner
    grant_response = client.patch(
        f"/v1/members/{producer_id}",
        headers=auth(admin_token),
        json={"role": "owner"},
    )
    assert grant_response.status_code == 403

    # Admin cannot revoke owner
    revoke_response = client.patch(
        f"/v1/members/{owner_id}",
        headers=auth(admin_token),
        json={"role": "admin"},
    )
    assert revoke_response.status_code == 403

    # Admin cannot invite an owner
    owner_invite_response = client.post(
        "/v1/members/invite",
        headers=auth(admin_token),
        json={"email": f"second-owner-{slug}@example.com", "role": "owner"},
    )
    assert owner_invite_response.status_code == 403

    # Admin cannot remove an owner
    remove_owner_response = client.delete(f"/v1/members/{owner_id}", headers=auth(admin_token))
    assert remove_owner_response.status_code == 403

    # Nobody can change their own role — not even the owner
    self_change_response = client.patch(
        f"/v1/members/{owner_id}",
        headers=auth(owner_token),
        json={"role": "admin"},
    )
    assert self_change_response.status_code == 400

    # Unknown roles are rejected
    bad_role_response = client.patch(
        f"/v1/members/{admin_id}",
        headers=auth(owner_token),
        json={"role": "superuser"},
    )
    assert bad_role_response.status_code == 400

    # Owner can grant owner
    promote_response = client.patch(
        f"/v1/members/{admin_id}",
        headers=auth(owner_token),
        json={"role": "owner"},
    )
    assert promote_response.status_code == 200
    assert promote_response.json()["role"] == "owner"


def test_last_owner_protection():
    owner_token, slug, _ = register_org("last-owner")
    admin_token = invite_and_accept(owner_token, f"admin-{slug}@example.com", "admin")
    owner_id = get_user_id(owner_token)
    admin_id = get_user_id(admin_token)

    # Sole owner cannot remove their own membership
    self_remove_response = client.delete(f"/v1/members/{owner_id}", headers=auth(owner_token))
    assert self_remove_response.status_code == 409

    # Promote the admin so there are two owners
    promote_response = client.patch(
        f"/v1/members/{admin_id}",
        headers=auth(owner_token),
        json={"role": "owner"},
    )
    assert promote_response.status_code == 200

    # With two owners, demoting one is allowed
    demote_response = client.patch(
        f"/v1/members/{owner_id}",
        headers=auth(admin_token),
        json={"role": "admin"},
    )
    assert demote_response.status_code == 200

    # The remaining owner is now protected again
    last_demote_response = client.patch(
        f"/v1/members/{admin_id}",
        headers=auth(owner_token),  # original owner is now an admin
        json={"role": "viewer"},
    )
    assert last_demote_response.status_code == 403  # admins cannot revoke owner

    last_remove_response = client.delete(f"/v1/members/{admin_id}", headers=auth(admin_token))
    assert last_remove_response.status_code == 409  # sole owner cannot be removed

    # An owner can remove a non-owner member
    remove_member_response = client.delete(f"/v1/members/{owner_id}", headers=auth(admin_token))
    assert remove_member_response.status_code == 204

    members_response = client.get("/v1/members", headers=auth(admin_token))
    assert members_response.status_code == 200
    assert len(members_response.json()) == 1
