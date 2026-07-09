export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  refresh_token?: string | null;
};

export type RegisterRequest = {
  organization_name: string;
  organization_slug: string;
  email: string;
  password: string;
  full_name?: string;
};

export type LoginRequest = {
  email: string;
  password: string;
  org_slug?: string;
};

export type UserContext = {
  user: {
    id: string;
    email: string;
    full_name: string | null;
    is_active: boolean;
  };
  organization_id: string;
  role: string;
};

export type Organization = {
  id: string;
  name: string;
  slug: string;
  plan: string;
};

export type OrgMembership = {
  organization: Organization;
  role: string;
};

export type LoginResponse = {
  access_token: string | null;
  token_type: "bearer";
  refresh_token?: string | null;
  organization?: Organization | null;
  role?: string | null;
  requires_org_selection: boolean;
  organizations: OrgMembership[];
};

export type SwitchOrgRequest = {
  org_slug: string;
};

export type Member = {
  user_id: string;
  email: string;
  full_name: string | null;
  role: string;
  joined_at: string;
};

export type MemberInviteRequest = {
  email: string;
  role: string;
};

export type MemberInviteResponse = {
  status: "member_added" | "invitation_created";
  email: string;
  role: string;
  invite_token: string | null;
  expires_at: string | null;
};

export type AcceptInviteRequest = {
  token: string;
  password: string;
  full_name?: string;
};

export type PlatformKey = {
  id: string;
  platform: string;
  display_name: string | null;
  masked_stream_key: string;
  is_active: boolean;
  rotated_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PlatformKeyCreate = {
  platform: string;
  display_name?: string;
  stream_key: string;
};

export type Stream = {
  id: string;
  organization_id: string;
  title: string | null;
  status: "scheduled" | "live" | "ended" | string;
  source: string;
  active_scene: string;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
};

export type StreamCreate = {
  title: string;
  source: string;
};

export type StreamDestinationStatus = {
  platform: string;
  status: string;
};

// Frame pushed by the metrics WebSocket (apps/api/app/routers/ws.py).
export type StreamMetrics = {
  type: "metrics";
  stream_id: string;
  status: "live" | "offline";
  bitrate_kbps: number;
  uptime_seconds: number;
  dropped_frames: number;
  viewer_count?: number;
  health_status: string;
  destinations: StreamDestinationStatus[];
};

// Response from stream start/stop: the stream plus relay outcome.
export type StreamActionResult = Stream & {
  ingest_url?: string | null;
  warning?: string | null;
};

// Archived broadcast recording (served from the media-server via the API).
export type Recording = {
  filename: string;
  size_bytes: number;
  modified_at: string;
};
