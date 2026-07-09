"use client";

import { Camera, CircleDot, MonitorUp, Square, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { captureSocketUrl } from "../lib/api";

type Props = {
  streamId: string;
  ingestKey: string;
  activeScene: string;
  orgSlug: string;
  onStatus: (message: string) => void;
};

type SourceKind = "camera" | "screen";

type StudioSource = {
  id: string;
  kind: SourceKind;
  label: string;
  stream: MediaStream;
  video: HTMLVideoElement;
};

type LayoutType = "single" | "side-by-side" | "pip";

type SceneLayout = {
  type: LayoutType;
  primary: string | null; // source id; null = first available
  secondary: string | null;
};

const LAYOUT_LABELS: Record<LayoutType, string> = {
  single: "Full frame",
  "side-by-side": "Side by side",
  pip: "Picture in picture"
};

const PROGRAM_WIDTH = 1280;
const PROGRAM_HEIGHT = 720;
const PROGRAM_FPS = 30;
const CHUNK_MILLISECONDS = 1000;

// Prefer H.264 in the browser so the server transcode is cheap; VP8 works too.
const RECORDER_MIME_CANDIDATES = [
  'video/webm;codecs="h264,opus"',
  'video/webm;codecs="vp8,opus"',
  "video/webm"
];

function pickRecorderMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return RECORDER_MIME_CANDIDATES.find((candidate) => MediaRecorder.isTypeSupported(candidate));
}

function makeSourceVideo(stream: MediaStream): HTMLVideoElement {
  const video = document.createElement("video");
  video.srcObject = stream;
  video.muted = true;
  video.playsInline = true;
  void video.play().catch(() => undefined);
  return video;
}

/** Crop-to-fill draw so every region is covered without letterboxing. */
function drawCover(
  ctx: CanvasRenderingContext2D,
  video: HTMLVideoElement,
  x: number,
  y: number,
  w: number,
  h: number
) {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) {
    ctx.fillStyle = "#0b0f16";
    ctx.fillRect(x, y, w, h);
    return;
  }
  const scale = Math.max(w / vw, h / vh);
  const sw = w / scale;
  const sh = h / scale;
  ctx.drawImage(video, (vw - sw) / 2, (vh - sh) / 2, sw, sh, x, y, w, h);
}

/**
 * The Studio: the system's own production layer. Multiple sources (cameras,
 * screen shares for slides/presentations/classes) are composited onto a
 * program canvas per-scene — full frame, side by side, or picture in
 * picture — and the composite is what goes on the air. Switching the
 * stream's scene switches the layout live.
 */
export default function Studio({ streamId, ingestKey, activeScene, orgSlug, onStatus }: Props) {
  const [sources, setSources] = useState<StudioSource[]>([]);
  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([]);
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
  const [cameraDeviceId, setCameraDeviceId] = useState("");
  const [audioDeviceId, setAudioDeviceId] = useState("");
  const [layouts, setLayouts] = useState<Record<string, SceneLayout>>({});
  const [broadcasting, setBroadcasting] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sourcesRef = useRef<StudioSource[]>([]);
  const layoutsRef = useRef<Record<string, SceneLayout>>({});
  const activeSceneRef = useRef(activeScene);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const drawTimerRef = useRef<number | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  const sourceSequenceRef = useRef(0);

  useEffect(() => {
    sourcesRef.current = sources;
    layoutsRef.current = layouts;
    activeSceneRef.current = activeScene;
  }, [sources, layouts, activeScene]);

  const layoutStorageKey = `pentecostal_live_layouts_${orgSlug}`;

  // Restore saved per-scene layouts once.
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(layoutStorageKey);
      if (saved) setLayouts(JSON.parse(saved) as Record<string, SceneLayout>);
    } catch {
      // corrupted saved layouts: start fresh
    }
  }, [layoutStorageKey]);

  const sceneLayout: SceneLayout = useMemo(
    () => layouts[activeScene] ?? { type: "single", primary: null, secondary: null },
    [layouts, activeScene]
  );

  function updateSceneLayout(patch: Partial<SceneLayout>) {
    setLayouts((previous) => {
      const current = previous[activeScene] ?? { type: "single", primary: null, secondary: null };
      const next = { ...previous, [activeScene]: { ...current, ...patch } };
      try {
        window.localStorage.setItem(layoutStorageKey, JSON.stringify(next));
      } catch {
        // storage full/blocked: layouts just won't persist
      }
      return next;
    });
  }

  function resolveSource(sourceId: string | null, fallbackIndex: number): StudioSource | null {
    const current = sourcesRef.current;
    return current.find((source) => source.id === sourceId) ?? current[fallbackIndex] ?? current[0] ?? null;
  }

  const renderProgram = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    ctx.fillStyle = "#0b0f16";
    ctx.fillRect(0, 0, PROGRAM_WIDTH, PROGRAM_HEIGHT);

    const layout =
      layoutsRef.current[activeSceneRef.current] ?? ({ type: "single", primary: null, secondary: null } as SceneLayout);
    const primary = resolveSource(layout.primary, 0);
    const secondary = resolveSource(layout.secondary, 1);

    if (!primary) {
      ctx.fillStyle = "#8b96a5";
      ctx.font = "600 28px Inter, system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("Add a camera or screen to begin", PROGRAM_WIDTH / 2, PROGRAM_HEIGHT / 2);
      return;
    }

    if (layout.type === "side-by-side" && secondary && secondary.id !== primary.id) {
      drawCover(ctx, primary.video, 0, 0, PROGRAM_WIDTH / 2, PROGRAM_HEIGHT);
      drawCover(ctx, secondary.video, PROGRAM_WIDTH / 2, 0, PROGRAM_WIDTH / 2, PROGRAM_HEIGHT);
      ctx.fillStyle = "#0b0f16";
      ctx.fillRect(PROGRAM_WIDTH / 2 - 2, 0, 4, PROGRAM_HEIGHT);
    } else if (layout.type === "pip" && secondary && secondary.id !== primary.id) {
      drawCover(ctx, primary.video, 0, 0, PROGRAM_WIDTH, PROGRAM_HEIGHT);
      const pipWidth = PROGRAM_WIDTH * 0.28;
      const pipHeight = (pipWidth * 9) / 16;
      const margin = 20;
      const x = PROGRAM_WIDTH - pipWidth - margin;
      const y = PROGRAM_HEIGHT - pipHeight - margin;
      ctx.fillStyle = "#f8fafc";
      ctx.fillRect(x - 3, y - 3, pipWidth + 6, pipHeight + 6);
      drawCover(ctx, secondary.video, x, y, pipWidth, pipHeight);
    } else {
      drawCover(ctx, primary.video, 0, 0, PROGRAM_WIDTH, PROGRAM_HEIGHT);
    }
  }, []);

  // Program render loop.
  useEffect(() => {
    drawTimerRef.current = window.setInterval(renderProgram, 1000 / PROGRAM_FPS);
    return () => {
      if (drawTimerRef.current !== null) window.clearInterval(drawTimerRef.current);
    };
  }, [renderProgram]);

  const stopBroadcast = useCallback(() => {
    const recorder = recorderRef.current;
    recorderRef.current = null;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    const socket = socketRef.current;
    socketRef.current = null;
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
    setBroadcasting(false);
  }, []);

  const closeStudio = useCallback(() => {
    stopBroadcast();
    sourcesRef.current.forEach((source) => source.stream.getTracks().forEach((track) => track.stop()));
    audioStreamRef.current?.getTracks().forEach((track) => track.stop());
    audioStreamRef.current = null;
    setSources([]);
  }, [stopBroadcast]);

  // Full teardown when the stream or key changes, or the panel unmounts.
  useEffect(() => closeStudio, [closeStudio, streamId, ingestKey]);

  async function refreshDeviceLists() {
    const devices = await navigator.mediaDevices.enumerateDevices();
    setVideoDevices(devices.filter((device) => device.kind === "videoinput"));
    setAudioDevices(devices.filter((device) => device.kind === "audioinput"));
  }

  async function ensureAudio() {
    if (audioStreamRef.current) return;
    audioStreamRef.current = await navigator.mediaDevices.getUserMedia({
      audio: audioDeviceId ? { deviceId: { exact: audioDeviceId } } : true
    });
  }

  async function addCamera() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: cameraDeviceId ? { deviceId: { exact: cameraDeviceId } } : true
      });
      await ensureAudio();
      await refreshDeviceLists();
      const track = stream.getVideoTracks()[0];
      sourceSequenceRef.current += 1;
      const source: StudioSource = {
        id: `camera-${sourceSequenceRef.current}`,
        kind: "camera",
        label: track?.label || `Camera ${sourcesRef.current.length + 1}`,
        stream,
        video: makeSourceVideo(stream)
      };
      setSources((previous) => [...previous, source]);
      onStatus(`${source.label} added to the studio.`);
    } catch {
      onStatus("Could not open the camera — check permissions and connections.");
    }
  }

  async function addScreen() {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
      await ensureAudio();
      sourceSequenceRef.current += 1;
      const source: StudioSource = {
        id: `screen-${sourceSequenceRef.current}`,
        kind: "screen",
        label: "Screen / slides",
        stream,
        video: makeSourceVideo(stream)
      };
      // Ending the share from the browser bar removes the source.
      stream.getVideoTracks()[0]?.addEventListener("ended", () => removeSource(source.id));
      setSources((previous) => [...previous, source]);
      onStatus("Screen share added to the studio.");
    } catch {
      onStatus("Could not share the screen — check permissions.");
    }
  }

  function removeSource(sourceId: string) {
    setSources((previous) => {
      const leaving = previous.find((source) => source.id === sourceId);
      leaving?.stream.getTracks().forEach((track) => track.stop());
      return previous.filter((source) => source.id !== sourceId);
    });
  }

  async function switchAudioDevice(deviceId: string) {
    setAudioDeviceId(deviceId);
    if (broadcasting) return; // takes effect on the next broadcast
    audioStreamRef.current?.getTracks().forEach((track) => track.stop());
    audioStreamRef.current = null;
    try {
      audioStreamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: deviceId ? { deviceId: { exact: deviceId } } : true
      });
    } catch {
      onStatus("Could not open that microphone.");
    }
  }

  function startBroadcast() {
    const canvas = canvasRef.current;
    if (!canvas || sourcesRef.current.length === 0) return;
    const mimeType = pickRecorderMimeType();
    if (!mimeType) {
      onStatus("This browser cannot encode video (MediaRecorder unsupported).");
      return;
    }

    const socket = new WebSocket(captureSocketUrl(streamId, ingestKey));
    socketRef.current = socket;

    socket.onmessage = () => {
      // First frame from the gateway confirms the encoder is up — start sending.
      if (recorderRef.current) return;
      const program = canvas.captureStream(PROGRAM_FPS);
      audioStreamRef.current?.getAudioTracks().forEach((track) => program.addTrack(track));
      const recorder = new MediaRecorder(program, {
        mimeType,
        videoBitsPerSecond: 4_500_000,
        audioBitsPerSecond: 160_000
      });
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0 && socket.readyState === WebSocket.OPEN) {
          socket.send(event.data);
        }
      };
      recorder.start(CHUNK_MILLISECONDS);
      recorderRef.current = recorder;
      setBroadcasting(true);
      onStatus("Program is on the air.");
    };

    socket.onclose = (event) => {
      socketRef.current = null;
      if (recorderRef.current) stopBroadcast();
      if (event.code === 4403) {
        onStatus("Broadcast rejected — restart the stream to get a fresh key.");
      } else if (event.code !== 1000) {
        onStatus("Program broadcast ended.");
      }
    };
  }

  const hasSecondSource = sources.length > 1;

  return (
    <div className="capture-studio">
      <div className="capture-preview">
        <canvas ref={canvasRef} width={PROGRAM_WIDTH} height={PROGRAM_HEIGHT} aria-label="Program output preview" />
        {broadcasting && (
          <span className="pill live capture-onair">
            <CircleDot size={12} /> ON AIR
          </span>
        )}
        <span className="feed-label">Program · scene: {activeScene}</span>
      </div>

      <div className="studio-sources">
        {sources.map((source) => (
          <span className="source-chip" key={source.id}>
            {source.kind === "camera" ? <Camera size={14} /> : <MonitorUp size={14} />}
            {source.label}
            <button
              className="chip-remove"
              onClick={() => removeSource(source.id)}
              disabled={broadcasting && sources.length === 1}
              title={`Remove ${source.label}`}
              aria-label={`Remove ${source.label}`}
            >
              <X size={12} />
            </button>
          </span>
        ))}
        {sources.length === 0 && <span className="empty">No sources yet.</span>}
      </div>

      <div className="capture-devices">
        <select
          value={cameraDeviceId}
          onChange={(event) => setCameraDeviceId(event.target.value)}
          aria-label="Camera to add"
        >
          <option value="">Default camera</option>
          {videoDevices.map((device) => (
            <option key={device.deviceId} value={device.deviceId}>
              {device.label || "Camera"}
            </option>
          ))}
        </select>
        <select
          value={audioDeviceId}
          onChange={(event) => void switchAudioDevice(event.target.value)}
          disabled={broadcasting}
          aria-label="Audio source"
        >
          <option value="">Default microphone</option>
          {audioDevices.map((device) => (
            <option key={device.deviceId} value={device.deviceId}>
              {device.label || "Microphone"}
            </option>
          ))}
        </select>
      </div>

      <div className="button-row studio-actions">
        <button onClick={() => void addCamera()}>
          <Camera size={18} /> Add camera
        </button>
        <button onClick={() => void addScreen()}>
          <MonitorUp size={18} /> Share screen
        </button>
        {!broadcasting ? (
          <button className="primary" onClick={startBroadcast} disabled={sources.length === 0}>
            <CircleDot size={18} /> Go live
          </button>
        ) : (
          <button className="danger" onClick={stopBroadcast}>
            <Square size={18} /> Stop broadcast
          </button>
        )}
      </div>

      <div className="layout-editor">
        <strong>“{activeScene}” scene layout</strong>
        <div className="layout-controls">
          <select
            value={sceneLayout.type}
            onChange={(event) => updateSceneLayout({ type: event.target.value as LayoutType })}
            aria-label="Layout for this scene"
          >
            {(Object.keys(LAYOUT_LABELS) as LayoutType[]).map((type) => (
              <option key={type} value={type} disabled={type !== "single" && !hasSecondSource}>
                {LAYOUT_LABELS[type]}
              </option>
            ))}
          </select>
          <select
            value={sceneLayout.primary ?? ""}
            onChange={(event) => updateSceneLayout({ primary: event.target.value || null })}
            aria-label="Main source for this scene"
          >
            <option value="">Main: first source</option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                Main: {source.label}
              </option>
            ))}
          </select>
          {sceneLayout.type !== "single" && (
            <select
              value={sceneLayout.secondary ?? ""}
              onChange={(event) => updateSceneLayout({ secondary: event.target.value || null })}
              aria-label="Second source for this scene"
            >
              <option value="">Second: next source</option>
              {sources.map((source) => (
                <option key={source.id} value={source.id}>
                  Second: {source.label}
                </option>
              ))}
            </select>
          )}
        </div>
        <span className="empty">
          Each scene remembers its layout — switch scenes on the stream to cut between them live.
        </span>
      </div>
    </div>
  );
}
