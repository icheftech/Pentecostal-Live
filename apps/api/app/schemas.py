from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=120)
    organization_slug: str = Field(pattern=r"^[a-z0-9-]{2,80}$")
    email: EmailStr
    password: str = Field(min_length=10)
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Optional — if the user belongs to multiple orgs, supply the target slug
    org_slug: str | None = None


class SwitchOrgRequest(BaseModel):
    org_slug: str


class AcceptInviteRequest(BaseModel):
    token: str = Field(min_length=10)
    password: str = Field(min_length=10)
    full_name: str | None = None


class OrgMembership(BaseModel):
    """A single org + the user's role in that org."""
    organization: "OrganizationOut"
    role: str


class LoginResponse(BaseModel):
    """
    Login can return one of two shapes:

    1. Token minted — access_token is set, organization and role are populated.
    2. Org selection required — access_token is None, requires_org_selection is True,
       organizations lists all orgs the user can enter. Client should re-POST /login
       with the chosen org_slug.
    """
    access_token: str | None = None
    token_type: str = "bearer"
    refresh_token: str | None = None
    organization: "OrganizationOut | None" = None
    role: str | None = None
    requires_org_selection: bool = False
    organizations: list[OrgMembership] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str | None
    is_active: bool


class MeResponse(BaseModel):
    user: UserOut
    organization_id: str
    role: str


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------

class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    plan: str


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

class MemberOut(BaseModel):
    user_id: str
    email: EmailStr
    full_name: str | None
    role: str
    joined_at: datetime


class MemberInviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(min_length=2, max_length=60)


class MemberInviteResponse(BaseModel):
    """
    Two outcomes:

    1. status="member_added" — the invited email already had an account, so the
       membership was created immediately. invite_token is None.
    2. status="invitation_created" — an Invitation row was created and
       invite_token holds the one-time token the admin shares with the invitee.
    """
    status: str
    email: EmailStr
    role: str
    invite_token: str | None = None
    expires_at: datetime | None = None


class MemberRoleUpdate(BaseModel):
    role: str = Field(min_length=2, max_length=60)


# ---------------------------------------------------------------------------
# Platform keys
# ---------------------------------------------------------------------------

class PlatformKeyCreate(BaseModel):
    platform: str = Field(min_length=2, max_length=80)
    stream_key: str = Field(min_length=4)
    display_name: str | None = None


class PlatformKeyUpdate(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None


class PlatformKeyRotate(BaseModel):
    stream_key: str = Field(min_length=4)


class PlatformKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    platform: str
    display_name: str | None
    masked_stream_key: str
    is_active: bool
    rotated_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Streams
# ---------------------------------------------------------------------------

class StreamCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    source: str = "screen"


class StreamSceneRequest(BaseModel):
    scene: str = Field(min_length=2, max_length=80)


class StreamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    title: str | None
    status: str
    source: str
    active_scene: str
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StreamActionOut(StreamOut):
    """Response for start/stop: stream state plus the media relay outcome.

    warning is set when the media-server could not be reached or refused the
    request — the stream state still changed; churches are never hard-blocked
    from toggling state mid-service.
    """

    ingest_url: str | None = None
    warning: str | None = None


class StreamDestinationStatus(BaseModel):
    platform: str
    status: str


class StreamMetricsOut(BaseModel):
    stream_id: str
    # Media-server status for the stream: "live" or "offline"
    status: str = "offline"
    bitrate_kbps: int
    viewer_count: int
    uptime_seconds: int = 0
    dropped_frames: int
    health_status: str
    destinations: list[StreamDestinationStatus] = Field(default_factory=list)


# Rebuild forward refs after all models are defined
LoginResponse.model_rebuild()
OrgMembership.model_rebuild()


class RecordingOut(BaseModel):
    filename: str
    size_bytes: int
    modified_at: str
