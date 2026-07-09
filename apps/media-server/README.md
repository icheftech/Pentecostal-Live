# Pentecostal Live Media Server

Standalone FastAPI service that owns the FFmpeg relay processes. The main API
(`apps/api`) calls it when a producer starts/stops a stream; it fans the RTMP
ingest out to every configured platform and optionally writes an HLS output
for the church website player.

```
OBS / encoder
   │  rtmp://<ingest-host>:1935/live/<ingest_key>
   ▼
nginx-rtmp ingest (infra/nginx)
   │  (media-server pulls the ingest)
   ▼
media-server ffmpeg relay (this service, one process per stream)
   ├─► YouTube / Facebook / TikTok / Instagram (RTMP, stream copy)
   └─► HLS output  →  $PENTECOSTAL_LIVE_HLS_ROOT/<stream_id>/index.m3u8
```

FFmpeg argv construction lives in `services/ffmpeg` (`pentecostal_ffmpeg`),
which also holds the canonical platform RTMP base URLs.

## Authentication

Every endpoint except `GET /health` requires the shared-secret header:

```
X-Media-Server-Token: <value of PENTECOSTAL_LIVE_MEDIA_SERVER_TOKEN>
```

Requests with a missing or wrong token get `401`.

## Endpoints

### POST /relays/{stream_id}/start

Body:

```json
{
  "ingest_url": "rtmp://localhost:1935/live/<ingest_key>",
  "destinations": [
    {"platform": "youtube", "rtmp_url": "rtmp://a.rtmp.youtube.com/live2", "stream_key": "xxxx"},
    {"platform": "facebook", "rtmp_url": "rtmps://live-api-s.facebook.com:443/rtmp", "stream_key": "yyyy"}
  ],
  "hls": true
}
```

- `rtmp_url` may be omitted; the standard base URL is then resolved from the
  platform id (`youtube`, `facebook`, `tiktok`, `instagram`, `pmbc`). Unknown
  platform without `rtmp_url` → `422`.
- At least one destination or `hls: true` is required, otherwise `422`.
- Starting a stream that already has a relay terminates the old process and
  starts a fresh one (idempotent restart; response has `"restarted": true`).

Response `200`:

```json
{"stream_id": "…", "status": "live", "destinations": [{"platform": "youtube", "status": "connected"}], "hls": true, "restarted": false}
```

### POST /relays/{stream_id}/stop

Terminates the relay (SIGTERM, then SIGKILL after 10s). Idempotent — stopping
a stream with no relay returns `200` with `"was_running": false`.

```json
{"stream_id": "…", "status": "offline", "was_running": true}
```

### GET /streams/{stream_id}/stats

**Stable contract — the main API consumes this exact shape. Do not change
field names or types without coordinating with `apps/api`.**

```json
{
  "stream_id": "…",
  "status": "live",
  "bitrate_kbps": 4501,
  "uptime_seconds": 322,
  "dropped_frames": 7,
  "destinations": [
    {"platform": "youtube", "status": "connected"},
    {"platform": "facebook", "status": "connected"}
  ]
}
```

- `status` is `"live"` while the ffmpeg process is running, otherwise
  `"offline"`.
- `bitrate_kbps`, `dropped_frames` are parsed live from ffmpeg
  `-progress pipe:1` output; `uptime_seconds` is wall time since relay start.
- When there is no relay (or ffmpeg exited): `status: "offline"` and all
  numbers are `0`; `destinations` is `[]` for unknown streams, or the last
  known destinations each with `status: "offline"`.
- Destination `status` is `"connected"` while the relay runs (per-destination
  RTMP health is not individually probed yet; `onfail=ignore` keeps the other
  outputs alive if one platform drops).

### GET /health

Unauthenticated liveness probe.

## Configuration (env vars)

| Variable | Default | Purpose |
| --- | --- | --- |
| `PENTECOSTAL_LIVE_MEDIA_SERVER_TOKEN` | `change_me_media_server_token` | Shared secret for `X-Media-Server-Token` |
| `PENTECOSTAL_LIVE_FFMPEG_BINARY` | `ffmpeg` | Path to the ffmpeg binary |
| `PENTECOSTAL_LIVE_HLS_ROOT` | `./data/hls` | Directory HLS playlists/segments are written to |

## Run locally

```bash
cd apps/media-server
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt ../../services/ffmpeg
uvicorn media_server.main:app --port 8001
```

## Tests

FFmpeg is not required — the subprocess is faked and progress output is canned.

```bash
cd apps/media-server && pytest
```

## Docker

Build from the repo root (the image installs `services/ffmpeg` and real ffmpeg):

```bash
docker build -f apps/media-server/Dockerfile -t pentecostal-live-media-server .
docker run -p 8001:8001 -e PENTECOSTAL_LIVE_MEDIA_SERVER_TOKEN=… pentecostal-live-media-server
```
