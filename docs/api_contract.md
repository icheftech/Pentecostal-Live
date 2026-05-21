# Pentecostal Live Phase 1 API Contract

Base path: `/v1`

## Auth

- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `GET /v1/auth/me`

## Organizations

- `GET /v1/organizations/current`
- `PATCH /v1/organizations/current`

## Platform Keys

- `GET /v1/platform-keys`
- `POST /v1/platform-keys`
- `PATCH /v1/platform-keys/{platform_key_id}`
- `DELETE /v1/platform-keys/{platform_key_id}`
- `POST /v1/platform-keys/{platform_key_id}/rotate`
- `POST /v1/platform-keys/{platform_key_id}/test`

Frontend must only receive masked keys, for example: `••••••••ABCD`.

## Streams

- `GET /v1/streams`
- `POST /v1/streams`
- `POST /v1/streams/{stream_id}/start`
- `POST /v1/streams/{stream_id}/stop`
- `POST /v1/streams/{stream_id}/scene`
- `GET /v1/streams/{stream_id}/metrics`

## WebSocket

- `WS /v1/ws/streams/{stream_id}`

Events:

```json
{ "type": "stream_started", "stream_id": "uuid", "platforms": ["youtube", "pmbc"] }
{ "type": "metrics", "bitrate_kbps": 5980, "viewer_count": 124, "dropped_frames": 0 }
{ "type": "scene_changed", "scene": "main" }
{ "type": "stream_stopped", "uptime_seconds": 3600 }
```
