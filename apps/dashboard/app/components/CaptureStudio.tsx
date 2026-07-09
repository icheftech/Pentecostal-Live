"use client";

import { Camera, CircleDot, MonitorUp, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { captureSocketUrl } from "../lib/api";

type Props = {
  streamId: string;
  ingestKey: string;
  onStatus: (message: string) => void;
};

// Prefer H.264 in the browser so the server transcode is cheap; VP8 works too.
const RECORDER_MIME_CANDIDATES = [
  'video/webm;codecs="h264,opus"',
  'video/webm;codecs="vp8,opus"',
  "video/webm"
];

const CHUNK_MILLISECONDS = 1000;

function pickRecorderMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return RECORDER_MIME_CANDIDATES.find((candidate) => MediaRecorder.isTypeSupported(candidate));
}

/**
 * The system's own capture layer: webcams and HDMI/SDI sources (via USB
 * capture devices, which the OS presents as cameras) are captured in the
 * browser and streamed to the media-server capture gateway — no OBS or other
 * third-party encoder required.
 */
export default function CaptureStudio({ streamId, ingestKey, onStatus }: Props) {
  const [sourceType, setSourceType] = useState<"camera" | "screen">("camera");
  const [videoDevices, setVideoDevices] = useState<MediaDeviceInfo[]>([]);
  const [audioDevices, setAudioDevices] = useState<MediaDeviceInfo[]>([]);
  const [videoDeviceId, setVideoDeviceId] = useState("");
  const [audioDeviceId, setAudioDeviceId] = useState("");
  const [previewing, setPreviewing] = useState(false);
  const [broadcasting, setBroadcasting] = useState(false);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  const stopBroadcast = useCallback(() => {
    const recorder = recorderRef.current;
    recorderRef.current = null;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
    const socket = socketRef.current;
    socketRef.current = null;
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
    setBroadcasting(false);
  }, []);

  const stopPreview = useCallback(() => {
    stopBroadcast();
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setPreviewing(false);
  }, [stopBroadcast]);

  // Tear everything down when the panel unmounts or the stream/key changes.
  useEffect(() => stopPreview, [stopPreview, streamId, ingestKey]);

  async function startPreview(nextSourceType: "camera" | "screen" = sourceType) {
    try {
      let stream: MediaStream;
      if (nextSourceType === "screen") {
        // Screen/slides source (lyrics, announcements) + the selected microphone.
        const display = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
        const mic = await navigator.mediaDevices.getUserMedia({
          audio: audioDeviceId ? { deviceId: { exact: audioDeviceId } } : true
        });
        stream = new MediaStream([...display.getVideoTracks(), ...mic.getAudioTracks()]);
      } else {
        stream = await navigator.mediaDevices.getUserMedia({
          video: videoDeviceId ? { deviceId: { exact: videoDeviceId } } : true,
          audio: audioDeviceId ? { deviceId: { exact: audioDeviceId } } : true
        });
      }
      mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setSourceType(nextSourceType);
      setPreviewing(true);
      // Labels are only populated after permission is granted.
      const devices = await navigator.mediaDevices.enumerateDevices();
      setVideoDevices(devices.filter((device) => device.kind === "videoinput"));
      setAudioDevices(devices.filter((device) => device.kind === "audioinput"));
      onStatus(nextSourceType === "screen" ? "Screen share preview ready." : "Camera preview ready.");
    } catch {
      onStatus(
        nextSourceType === "screen"
          ? "Could not share the screen — check permissions."
          : "Could not open the camera — check permissions and connections."
      );
    }
  }

  function startBroadcast() {
    const mediaStream = mediaStreamRef.current;
    if (!mediaStream) return;
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
      const recorder = new MediaRecorder(mediaStream, {
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
      onStatus("Camera is on the air.");
    };

    socket.onclose = (event) => {
      socketRef.current = null;
      if (recorderRef.current) {
        stopBroadcast();
      }
      if (event.code === 4403) {
        onStatus("Capture rejected — restart the stream to get a fresh key.");
      } else if (broadcasting || event.code !== 1000) {
        onStatus("Camera broadcast ended.");
      }
    };
  }

  return (
    <div className="capture-studio">
      <div className="capture-preview">
        <video ref={videoRef} autoPlay muted playsInline />
        {!previewing && (
          <div className="capture-placeholder">
            <Camera size={40} />
            <span>Connect a webcam or an HDMI/SDI capture device and open the camera — or share a screen for slides and lyrics.</span>
          </div>
        )}
        {broadcasting && (
          <span className="pill live capture-onair">
            <CircleDot size={12} /> ON AIR
          </span>
        )}
      </div>

      {previewing && (videoDevices.length > 0 || audioDevices.length > 0) && (
        <div className="capture-devices">
          <select
            value={videoDeviceId}
            onChange={(event) => setVideoDeviceId(event.target.value)}
            disabled={broadcasting || sourceType === "screen"}
            aria-label="Video source"
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
            onChange={(event) => setAudioDeviceId(event.target.value)}
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
      )}

      <div className="button-row">
        {!previewing ? (
          <>
            <button className="primary" onClick={() => void startPreview("camera")}>
              <Camera size={18} /> Open camera
            </button>
            <button onClick={() => void startPreview("screen")}>
              <MonitorUp size={18} /> Share screen
            </button>
          </>
        ) : (
          <>
            <button onClick={() => void startPreview(sourceType)} disabled={broadcasting}>
              Apply source
            </button>
            <button
              onClick={() => void startPreview(sourceType === "camera" ? "screen" : "camera")}
              disabled={broadcasting}
            >
              {sourceType === "camera" ? <MonitorUp size={18} /> : <Camera size={18} />}
              {sourceType === "camera" ? "Switch to screen" : "Switch to camera"}
            </button>
            {!broadcasting ? (
              <button className="primary" onClick={startBroadcast}>
                <CircleDot size={18} /> Go live from this camera
              </button>
            ) : (
              <button className="danger" onClick={stopBroadcast}>
                <Square size={18} /> Stop camera broadcast
              </button>
            )}
            <button onClick={stopPreview} disabled={broadcasting}>
              Close camera
            </button>
          </>
        )}
      </div>
    </div>
  );
}
