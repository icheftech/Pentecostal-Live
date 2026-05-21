"use client";

import { Activity, KeyRound, LogOut, Radio, RotateCw, ShieldCheck, Video } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import type { Organization, PlatformKey, Stream, UserContext } from "@pentecostal-live/types";

const tokenStorageKey = "pentecostal_live_token";
const defaultScenes = ["main", "sermon", "worship", "altar"];

export default function DashboardPage() {
  const [token, setToken] = useState<string | null>(null);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [me, setMe] = useState<UserContext | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [platformKeys, setPlatformKeys] = useState<PlatformKey[]>([]);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const liveStream = useMemo(() => streams.find((stream) => stream.status === "live"), [streams]);

  useEffect(() => {
    setToken(window.localStorage.getItem(tokenStorageKey));
  }, []);

  const refresh = useCallback(async (currentToken = token) => {
    if (!currentToken) return;
    const [userContext, org, keys, streamList] = await Promise.all([
      api.me(currentToken),
      api.organization(currentToken),
      api.platformKeys(currentToken),
      api.streams(currentToken)
    ]);
    setMe(userContext);
    setOrganization(org);
    setPlatformKeys(keys);
    setStreams(streamList);
  }, [token]);

  useEffect(() => {
    if (!token) return;
    void refresh(token);
  }, [refresh, token]);

  async function handleAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const data = new FormData(event.currentTarget);
    try {
      const response =
        mode === "login"
          ? await api.login({
              email: String(data.get("email")),
              password: String(data.get("password"))
            })
          : await api.register({
              organization_name: String(data.get("organizationName")),
              organization_slug: String(data.get("organizationSlug")),
              email: String(data.get("email")),
              password: String(data.get("password")),
              full_name: String(data.get("fullName") || "")
            });
      window.localStorage.setItem(tokenStorageKey, response.access_token);
      setToken(response.access_token);
      setMessage("Signed in.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Authentication failed");
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
    window.localStorage.removeItem(tokenStorageKey);
    setToken(null);
    setMe(null);
    setOrganization(null);
    setPlatformKeys([]);
    setStreams([]);
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
            <label>
              Email
              <input name="email" type="email" placeholder="producer@example.com" required />
            </label>
            <label>
              Password
              <input name="password" type="password" minLength={10} required />
            </label>
            <button className="primary" disabled={busy}>
              <ShieldCheck size={18} />
              {mode === "login" ? "Sign in" : "Create organization"}
            </button>
          </form>
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

        <div className="panel production">
          <div className="panel-title">
            <Activity size={20} />
            <h2>Live monitor</h2>
          </div>
          <div className="monitor">
            <Radio size={52} />
            <strong>{liveStream?.title ?? "No active broadcast"}</strong>
            <span>{liveStream ? "RTMP/HLS handoff ready for media server integration." : "Start a stream to arm metrics."}</span>
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
