"use client";

import {
  Activity,
  Copy,
  KeyRound,
  LogOut,
  Radio,
  RotateCw,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
  Video
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, streamMetricsSocketUrl } from "./lib/api";
import type {
  Member,
  MemberInviteResponse,
  Organization,
  OrgMembership,
  PlatformKey,
  Stream,
  StreamMetrics,
  UserContext
} from "@pentecostal-live/types";

const tokenStorageKey = "pentecostal_live_token";
const refreshTokenStorageKey = "pentecostal_live_refresh_token";
const defaultScenes = ["main", "sermon", "worship", "altar"];

export default function DashboardPage() {
  const [token, setToken] = useState<string | null>(null);
  const [mode, setMode] = useState<"login" | "register" | "invite">("login");
  const [me, setMe] = useState<UserContext | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [platformKeys, setPlatformKeys] = useState<PlatformKey[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [myOrgs, setMyOrgs] = useState<OrgMembership[]>([]);
  const [orgChoices, setOrgChoices] = useState<OrgMembership[] | null>(null);
  const [pendingLogin, setPendingLogin] = useState<{ email: string; password: string } | null>(null);
  const [inviteToken, setInviteToken] = useState("");
  const [inviteResult, setInviteResult] = useState<MemberInviteResponse | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [liveMetrics, setLiveMetrics] = useState<StreamMetrics | null>(null);

  const liveStream = useMemo(() => streams.find((stream) => stream.status === "live"), [streams]);
  const liveStreamId = liveStream?.id ?? null;

  // Live metrics over the authenticated WebSocket while a stream is live.
  useEffect(() => {
    if (!token || !liveStreamId) {
      setLiveMetrics(null);
      return;
    }
    const socket = new WebSocket(streamMetricsSocketUrl(liveStreamId, token));
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(String(event.data)) as StreamMetrics;
        if (payload.type === "metrics") {
          setLiveMetrics(payload);
        }
      } catch {
        // ignore malformed frames
      }
    };
    socket.onclose = () => setLiveMetrics(null);
    return () => {
      socket.onclose = null;
      socket.close();
      setLiveMetrics(null);
    };
  }, [token, liveStreamId]);
  const canManageMembers = me?.role === "owner" || me?.role === "admin";
  const assignableRoles = useMemo(
    () => (me?.role === "owner" ? ["owner", "admin", "producer", "viewer"] : ["admin", "producer", "viewer"]),
    [me?.role]
  );

  useEffect(() => {
    setToken(window.localStorage.getItem(tokenStorageKey));
    const urlToken = new URLSearchParams(window.location.search).get("invite_token");
    if (urlToken) {
      setInviteToken(urlToken);
      setMode("invite");
    }
  }, []);

  const loadAll = useCallback(async (currentToken: string) => {
    const [userContext, org, keys, streamList, memberList, orgList] = await Promise.all([
      api.me(currentToken),
      api.organization(currentToken),
      api.platformKeys(currentToken),
      api.streams(currentToken),
      api.members(currentToken),
      api.myOrgs(currentToken)
    ]);
    setMe(userContext);
    setOrganization(org);
    setPlatformKeys(keys);
    setStreams(streamList);
    setMembers(memberList);
    setMyOrgs(orgList);
  }, []);

  // Trade the stored refresh token for a new access/refresh pair.
  // Returns the new access token, or null if the session can't be renewed.
  const renewSession = useCallback(async (): Promise<string | null> => {
    const storedRefreshToken = window.localStorage.getItem(refreshTokenStorageKey);
    if (!storedRefreshToken) return null;
    try {
      const pair = await api.refreshToken(storedRefreshToken);
      window.localStorage.setItem(tokenStorageKey, pair.access_token);
      if (pair.refresh_token) {
        window.localStorage.setItem(refreshTokenStorageKey, pair.refresh_token);
      }
      setToken(pair.access_token);
      return pair.access_token;
    } catch {
      return null;
    }
  }, []);

  const refresh = useCallback(async (currentToken = token) => {
    if (!currentToken) return;
    try {
      await loadAll(currentToken);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        const renewedToken = await renewSession();
        if (renewedToken) {
          await loadAll(renewedToken);
          return;
        }
        signOut();
        setMessage("Session expired — please sign in again.");
        return;
      }
      throw error;
    }
  }, [token, loadAll, renewSession]);

  useEffect(() => {
    if (!token) return;
    void refresh(token);
  }, [refresh, token]);

  function adoptToken(accessToken: string, refreshToken?: string | null) {
    window.localStorage.setItem(tokenStorageKey, accessToken);
    if (refreshToken) {
      window.localStorage.setItem(refreshTokenStorageKey, refreshToken);
    }
    setToken(accessToken);
    setOrgChoices(null);
    setPendingLogin(null);
    setMessage("Signed in.");
  }

  async function handleAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const data = new FormData(event.currentTarget);
    try {
      if (mode === "login") {
        const email = String(data.get("email"));
        const password = String(data.get("password"));
        const response = await api.login({ email, password });
        if (response.requires_org_selection) {
          setOrgChoices(response.organizations);
          setPendingLogin({ email, password });
          setMessage("Choose an organization to continue.");
          return;
        }
        if (!response.access_token) {
          setMessage("Login failed.");
          return;
        }
        adoptToken(response.access_token, response.refresh_token);
      } else if (mode === "register") {
        const response = await api.register({
          organization_name: String(data.get("organizationName")),
          organization_slug: String(data.get("organizationSlug")),
          email: String(data.get("email")),
          password: String(data.get("password")),
          full_name: String(data.get("fullName") || "")
        });
        adoptToken(response.access_token, response.refresh_token);
      } else {
        const response = await api.acceptInvite({
          token: inviteToken,
          password: String(data.get("password")),
          full_name: String(data.get("fullName") || "")
        });
        window.history.replaceState(null, "", window.location.pathname);
        adoptToken(response.access_token, response.refresh_token);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleOrgChoice(orgSlug: string) {
    if (!pendingLogin) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await api.login({ ...pendingLogin, org_slug: orgSlug });
      if (!response.access_token) {
        setMessage("Login failed.");
        return;
      }
      adoptToken(response.access_token, response.refresh_token);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleSwitchOrg(orgSlug: string) {
    if (!token || orgSlug === organization?.slug) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await api.switchOrg(token, orgSlug);
      if (!response.access_token) {
        setMessage("Could not switch organization.");
        return;
      }
      setInviteResult(null);
      window.localStorage.setItem(tokenStorageKey, response.access_token);
      if (response.refresh_token) {
        window.localStorage.setItem(refreshTokenStorageKey, response.refresh_token);
      }
      setToken(response.access_token);
      setMessage(`Switched to ${response.organization?.name ?? orgSlug}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not switch organization");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setBusy(true);
    const data = new FormData(event.currentTarget);
    try {
      await api.createPlatformKey(token, {
        platform: String(data.get("platform")),
        display_name: String(data.get("displayName") || ""),
        stream_key: String(data.get("streamKey"))
      });
      event.currentTarget.reset();
      await refresh();
      setMessage("Platform key stored securely.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not save platform key");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateStream(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setBusy(true);
    const data = new FormData(event.currentTarget);
    try {
      await api.createStream(token, { title: String(data.get("title")), source: "screen" });
      event.currentTarget.reset();
      await refresh();
      setMessage("Stream scheduled.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not create stream");
    } finally {
      setBusy(false);
    }
  }

  async function handleInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setBusy(true);
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const response = await api.inviteMember(token, {
        email: String(data.get("inviteEmail")),
        role: String(data.get("inviteRole"))
      });
      form.reset();
      setInviteResult(response);
      await refresh();
      setMessage(
        response.status === "member_added"
          ? `${response.email} added as ${response.role}.`
          : `Invitation created for ${response.email}.`
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not invite member");
    } finally {
      setBusy(false);
    }
  }

  async function handleRoleChange(userId: string, role: string) {
    if (!token) return;
    setBusy(true);
    try {
      await api.updateMemberRole(token, userId, role);
      await refresh();
      setMessage("Member role updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not update member role");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveMember(userId: string, email: string) {
    if (!token) return;
    setBusy(true);
    try {
      await api.removeMember(token, userId);
      await refresh();
      setMessage(`${email} removed from the organization.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not remove member");
    } finally {
      setBusy(false);
    }
  }

  async function copyInviteLink(link: string) {
    try {
      await navigator.clipboard.writeText(link);
      setMessage("Invite link copied to clipboard.");
    } catch {
      setMessage("Could not copy — select the link text manually.");
    }
  }

  async function updateStream(action: () => Promise<Stream>) {
    setBusy(true);
    try {
      await action();
      await refresh();
      setMessage("Stream updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Stream action failed");
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    const storedRefreshToken = window.localStorage.getItem(refreshTokenStorageKey);
    if (storedRefreshToken) {
      // Best-effort server-side revocation; local sign-out proceeds regardless.
      void api.logout(storedRefreshToken).catch(() => undefined);
    }
    window.localStorage.removeItem(refreshTokenStorageKey);
    window.localStorage.removeItem(tokenStorageKey);
    setToken(null);
    setMe(null);
    setOrganization(null);
    setPlatformKeys([]);
    setStreams([]);
    setMembers([]);
    setMyOrgs([]);
    setOrgChoices(null);
    setPendingLogin(null);
    setInviteResult(null);
  }

  if (!token) {
    return (
      <main className="auth-page">
        <section className="auth-panel">
          <div>
            <p className="eyebrow">Pentecostal Live</p>
            <h1>Broadcast command center</h1>
            <p className="lede">
              Secure org-scoped livestream control for platform keys, scenes, and service broadcasts.
            </p>
          </div>
          {orgChoices ? (
            <div className="stack">
              <p className="lede">You belong to multiple organizations. Choose one to continue.</p>
              <div className="org-picker">
                {orgChoices.map(({ organization: org, role }) => (
                  <button key={org.id} onClick={() => void handleOrgChoice(org.slug)} disabled={busy}>
                    <span>{org.name}</span>
                    <span className="pill">{role}</span>
                  </button>
                ))}
              </div>
              <button
                className="secondary"
                onClick={() => {
                  setOrgChoices(null);
                  setPendingLogin(null);
                  setMessage("");
                }}
              >
                Back to login
              </button>
            </div>
          ) : (
            <>
              <div className="mode-switch" role="tablist" aria-label="Authentication mode">
                <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
                  Login
                </button>
                <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
                  Register
                </button>
              </div>
              <form className="stack" onSubmit={handleAuth}>
                {mode === "register" && (
                  <>
                    <label>
                      Organization
                      <input name="organizationName" placeholder="PMBC Media" required />
                    </label>
                    <label>
                      Organization slug
                      <input name="organizationSlug" placeholder="pmbc-media" required />
                    </label>
                    <label>
                      Full name
                      <input name="fullName" placeholder="Production Lead" />
                    </label>
                  </>
                )}
                {mode === "invite" && (
                  <>
                    <p className="lede">You have been invited to join an organization. Set up your account.</p>
                    <label>
                      Invite token
                      <input
                        name="inviteToken"
                        value={inviteToken}
                        onChange={(event) => setInviteToken(event.target.value)}
                        placeholder="Paste your invite token"
                        required
                      />
                    </label>
                    <label>
                      Full name
                      <input name="fullName" placeholder="Volunteer Producer" />
                    </label>
                  </>
                )}
                {mode !== "invite" && (
                  <label>
                    Email
                    <input name="email" type="email" placeholder="producer@example.com" required />
                  </label>
                )}
                <label>
                  Password
                  <input name="password" type="password" minLength={10} required />
                </label>
                <button className="primary" disabled={busy}>
                  <ShieldCheck size={18} />
                  {mode === "login" ? "Sign in" : mode === "register" ? "Create organization" : "Accept invite"}
                </button>
              </form>
              {mode === "invite" && (
                <button className="secondary" onClick={() => setMode("login")}>
                  Back to login
                </button>
              )}
            </>
          )}
          {message && <p className="message">{message}</p>}
        </section>
      </main>
    );
  }

  return (
    <main className="dashboard">
      <header className="topbar">
        <div>
          <p className="eyebrow">{organization?.plan ?? "pilot"} plan</p>
          <h1>{organization?.name ?? "Pentecostal Live"}</h1>
        </div>
        <div className="topbar-actions">
          {myOrgs.length > 1 && (
            <select
              className="org-switcher"
              value={organization?.slug ?? ""}
              onChange={(event) => void handleSwitchOrg(event.target.value)}
              disabled={busy}
              aria-label="Switch organization"
            >
              {myOrgs.map((membership) => (
                <option key={membership.organization.id} value={membership.organization.slug}>
                  {membership.organization.name}
                </option>
              ))}
            </select>
          )}
          <span>{me?.user.email}</span>
          <button className="icon-button" onClick={signOut} aria-label="Sign out" title="Sign out">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <section className="metrics-strip">
        <div>
          <span>Stream status</span>
          <strong>{liveStream ? "Live" : "Offline"}</strong>
        </div>
        <div>
          <span>Destinations</span>
          <strong>{platformKeys.filter((key) => key.is_active).length}</strong>
        </div>
        <div>
          <span>Active scene</span>
          <strong>{liveStream?.active_scene ?? "None"}</strong>
        </div>
      </section>

      <section className="workspace">
        <div className="panel">
          <div className="panel-title">
            <KeyRound size={20} />
            <h2>Platform keys</h2>
          </div>
          <form className="inline-form" onSubmit={handleCreateKey}>
            <input name="platform" placeholder="youtube" required />
            <input name="displayName" placeholder="Sunday YouTube" />
            <input name="streamKey" type="password" placeholder="Stream key" required />
            <button disabled={busy} title="Save platform key" aria-label="Save platform key">
              <KeyRound size={18} />
            </button>
          </form>
          <div className="table-list">
            {platformKeys.map((key) => (
              <div className="row" key={key.id}>
                <div>
                  <strong>{key.display_name || key.platform}</strong>
                  <span>{key.masked_stream_key}</span>
                </div>
                <span className={key.is_active ? "pill live" : "pill"}>{key.is_active ? "Active" : "Off"}</span>
              </div>
            ))}
            {platformKeys.length === 0 && <p className="empty">No platform keys configured.</p>}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">
            <Video size={20} />
            <h2>Streams</h2>
          </div>
          <form className="inline-form" onSubmit={handleCreateStream}>
            <input name="title" placeholder="Sunday Morning Worship" required />
            <button disabled={busy} title="Create stream" aria-label="Create stream">
              <Radio size={18} />
            </button>
          </form>
          <div className="table-list">
            {streams.map((stream) => (
              <div className="stream-row" key={stream.id}>
                <div>
                  <strong>{stream.title}</strong>
                  <span>{stream.status} · {stream.active_scene}</span>
                </div>
                <div className="button-row">
                  {stream.status === "live" ? (
                    <button onClick={() => updateStream(() => api.stopStream(token, stream.id))}>Stop</button>
                  ) : (
                    <button onClick={() => updateStream(() => api.startStream(token, stream.id))}>Start</button>
                  )}
                  {defaultScenes.map((scene) => (
                    <button
                      key={scene}
                      className={stream.active_scene === scene ? "selected" : ""}
                      onClick={() => updateStream(() => api.changeScene(token, stream.id, scene))}
                    >
                      {scene}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            {streams.length === 0 && <p className="empty">No streams scheduled.</p>}
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">
            <Users size={20} />
            <h2>Team</h2>
          </div>
          {canManageMembers && (
            <form className="inline-form invite-form" onSubmit={handleInvite}>
              <input name="inviteEmail" type="email" placeholder="member@example.com" required />
              <select name="inviteRole" defaultValue="viewer" aria-label="Invite role">
                {assignableRoles.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
              <button disabled={busy} title="Invite member" aria-label="Invite member">
                <UserPlus size={18} />
              </button>
            </form>
          )}
          {inviteResult?.status === "invitation_created" && inviteResult.invite_token && (
            <div className="invite-note">
              <div>
                <strong>Invitation for {inviteResult.email}</strong>
                <span>Share this link with them — invites are not emailed automatically.</span>
                <code>{`${window.location.origin}/?invite_token=${inviteResult.invite_token}`}</code>
              </div>
              <button
                className="icon-button"
                onClick={() =>
                  void copyInviteLink(`${window.location.origin}/?invite_token=${inviteResult.invite_token}`)
                }
                title="Copy invite link"
                aria-label="Copy invite link"
              >
                <Copy size={16} />
              </button>
            </div>
          )}
          <div className="table-list">
            {members.map((member) => {
              const canEditMember =
                canManageMembers &&
                member.user_id !== me?.user.id &&
                (me?.role === "owner" || member.role !== "owner");
              return (
                <div className="row" key={member.user_id}>
                  <div>
                    <strong>{member.full_name || member.email}</strong>
                    <span>{member.email}</span>
                  </div>
                  {canEditMember ? (
                    <div className="member-actions">
                      <select
                        value={member.role}
                        onChange={(event) => void handleRoleChange(member.user_id, event.target.value)}
                        disabled={busy}
                        aria-label={`Role for ${member.email}`}
                      >
                        {assignableRoles.map((role) => (
                          <option key={role} value={role}>
                            {role}
                          </option>
                        ))}
                      </select>
                      <button
                        className="icon-button danger"
                        onClick={() => void handleRemoveMember(member.user_id, member.email)}
                        disabled={busy}
                        title={`Remove ${member.email}`}
                        aria-label={`Remove ${member.email}`}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  ) : (
                    <span className={member.role === "owner" ? "pill live" : "pill"}>{member.role}</span>
                  )}
                </div>
              );
            })}
            {members.length === 0 && <p className="empty">No members yet.</p>}
          </div>
        </div>

        <div className="panel production">
          <div className="panel-title">
            <Activity size={20} />
            <h2>Live monitor</h2>
          </div>
          <div className="monitor">
            <Radio size={52} />
            <strong>{liveStream?.title ?? "No active broadcast"}</strong>
            {liveStream && liveMetrics ? (
              <>
                <span className={`pill ${liveMetrics.health_status === "excellent" ? "live" : ""}`}>
                  {liveMetrics.health_status}
                </span>
                <div className="monitor-stats">
                  <div>
                    <span>Bitrate</span>
                    <strong>{liveMetrics.bitrate_kbps} kbps</strong>
                  </div>
                  <div>
                    <span>Uptime</span>
                    <strong>
                      {Math.floor(liveMetrics.uptime_seconds / 60)}m {liveMetrics.uptime_seconds % 60}s
                    </strong>
                  </div>
                  <div>
                    <span>Dropped</span>
                    <strong>{liveMetrics.dropped_frames}</strong>
                  </div>
                </div>
                {liveMetrics.destinations.length > 0 && (
                  <div className="monitor-destinations">
                    {liveMetrics.destinations.map((destination) => (
                      <span
                        key={destination.platform}
                        className={destination.status === "connected" ? "pill live" : "pill"}
                      >
                        {destination.platform}
                      </span>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <span>{liveStream ? "Connecting to live metrics…" : "Start a stream to arm metrics."}</span>
            )}
          </div>
          <button className="secondary" onClick={() => refresh()} disabled={busy}>
            <RotateCw size={18} />
            Refresh
          </button>
        </div>
      </section>
      {message && <p className="toast">{message}</p>}
    </main>
  );
}
