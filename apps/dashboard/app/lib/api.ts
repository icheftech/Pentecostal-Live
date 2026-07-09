import type {
  AcceptInviteRequest,
  LoginRequest,
  LoginResponse,
  Member,
  MemberInviteRequest,
  MemberInviteResponse,
  Organization,
  OrgMembership,
  PlatformKey,
  PlatformKeyCreate,
  RegisterRequest,
  Stream,
  StreamCreate,
  TokenResponse,
  UserContext
} from "@pentecostal-live/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/v1";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers
    }
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new ApiError(body.detail ?? "Request failed", response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  login: (payload: LoginRequest) =>
    request<LoginResponse>("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  register: (payload: RegisterRequest) =>
    request<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(payload) }),
  acceptInvite: (payload: AcceptInviteRequest) =>
    request<TokenResponse>("/auth/accept-invite", { method: "POST", body: JSON.stringify(payload) }),
  refreshToken: (refreshToken: string) =>
    request<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken })
    }),
  logout: (refreshToken: string) =>
    request<void>("/auth/logout", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken })
    }),
  me: (token: string) => request<UserContext>("/auth/me", {}, token),
  myOrgs: (token: string) => request<OrgMembership[]>("/auth/orgs", {}, token),
  switchOrg: (token: string, orgSlug: string) =>
    request<LoginResponse>(
      "/auth/switch-org",
      { method: "POST", body: JSON.stringify({ org_slug: orgSlug }) },
      token
    ),
  members: (token: string) => request<Member[]>("/members", {}, token),
  inviteMember: (token: string, payload: MemberInviteRequest) =>
    request<MemberInviteResponse>(
      "/members/invite",
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),
  updateMemberRole: (token: string, userId: string, role: string) =>
    request<Member>(`/members/${userId}`, { method: "PATCH", body: JSON.stringify({ role }) }, token),
  removeMember: (token: string, userId: string) =>
    request<void>(`/members/${userId}`, { method: "DELETE" }, token),
  organization: (token: string) => request<Organization>("/organizations/current", {}, token),
  platformKeys: (token: string) => request<PlatformKey[]>("/platform-keys", {}, token),
  createPlatformKey: (token: string, payload: PlatformKeyCreate) =>
    request<PlatformKey>("/platform-keys", { method: "POST", body: JSON.stringify(payload) }, token),
  rotatePlatformKey: (token: string, id: string, streamKey: string) =>
    request<PlatformKey>(
      `/platform-keys/${id}/rotate`,
      { method: "POST", body: JSON.stringify({ stream_key: streamKey }) },
      token
    ),
  streams: (token: string) => request<Stream[]>("/streams", {}, token),
  createStream: (token: string, payload: StreamCreate) =>
    request<Stream>("/streams", { method: "POST", body: JSON.stringify(payload) }, token),
  startStream: (token: string, id: string) =>
    request<Stream>(`/streams/${id}/start`, { method: "POST" }, token),
  stopStream: (token: string, id: string) =>
    request<Stream>(`/streams/${id}/stop`, { method: "POST" }, token),
  changeScene: (token: string, id: string, scene: string) =>
    request<Stream>(`/streams/${id}/scene`, { method: "POST", body: JSON.stringify({ scene }) }, token)
};
