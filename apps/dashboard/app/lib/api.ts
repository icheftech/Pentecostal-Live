import type {
  LoginRequest,
  Organization,
  PlatformKey,
  PlatformKeyCreate,
  RegisterRequest,
  Stream,
  StreamCreate,
  TokenResponse,
  UserContext
} from "@pentecostal-live/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/v1";

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
    throw new Error(body.detail ?? "Request failed");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const api = {
  login: (payload: LoginRequest) =>
    request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  register: (payload: RegisterRequest) =>
    request<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(payload) }),
  me: (token: string) => request<UserContext>("/auth/me", {}, token),
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

