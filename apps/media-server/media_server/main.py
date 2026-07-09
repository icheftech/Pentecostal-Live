import asyncio
import hmac
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, status

from media_server import schemas
from media_server.capture import CaptureManager
from media_server.config import get_settings
from media_server.relay import RelayManager
from pentecostal_ffmpeg import Destination, build_destination_url, resolve_rtmp_url

logger = logging.getLogger("media_server.main")

settings = get_settings()
relay_manager = RelayManager(
    ffmpeg_binary=settings.ffmpeg_binary,
    hls_root=settings.hls_root,
)
capture_manager = CaptureManager(ffmpeg_binary=settings.ffmpeg_binary)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    capture_manager.stop_all()
    relay_manager.stop_all()


app = FastAPI(title="Pentecostal Live Media Server", version="0.1.0", lifespan=lifespan)


def require_token(
    x_media_server_token: str | None = Header(default=None, alias="X-Media-Server-Token"),
) -> None:
    expected = get_settings().media_server_token
    if x_media_server_token is None or not hmac.compare_digest(
        x_media_server_token, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-Media-Server-Token",
        )


@app.get("/health")
def health():
    return {"status": "ok", "service": "pentecostal-live-media-server"}


@app.post(
    "/relays/{stream_id}/start",
    response_model=schemas.RelayStartResponse,
    dependencies=[Depends(require_token)],
)
def start_relay(stream_id: str, payload: schemas.RelayStartRequest):
    destinations: list[Destination] = []
    skipped: list[str] = []
    for item in payload.destinations:
        rtmp_url = item.rtmp_url or resolve_rtmp_url(item.platform)
        if not rtmp_url:
            # One unknown platform must never block the whole broadcast.
            skipped.append(item.platform)
            continue
        destinations.append(
            Destination(
                platform=item.platform,
                url=build_destination_url(rtmp_url, item.stream_key),
            )
        )

    if not destinations and not payload.hls:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Relay needs at least one resolvable destination or hls=true",
        )

    try:
        handle, restarted = relay_manager.start(
            stream_id=stream_id,
            ingest_url=payload.ingest_url,
            destinations=destinations,
            hls=payload.hls,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ffmpeg binary not available: {exc}",
        ) from exc

    return schemas.RelayStartResponse(
        stream_id=stream_id,
        status="live",
        destinations=[
            {"platform": destination.platform, "status": "connected"}
            for destination in handle.destinations
        ]
        + [{"platform": platform, "status": "skipped_unknown_platform"} for platform in skipped],
        hls=payload.hls,
        restarted=restarted,
    )


@app.post(
    "/relays/{stream_id}/stop",
    response_model=schemas.RelayStopResponse,
    dependencies=[Depends(require_token)],
)
def stop_relay(stream_id: str):
    was_running = relay_manager.stop(stream_id)
    return schemas.RelayStopResponse(
        stream_id=stream_id,
        status="offline",
        was_running=was_running,
    )


@app.get(
    "/streams/{stream_id}/stats",
    response_model=schemas.StreamStats,
    dependencies=[Depends(require_token)],
)
def stream_stats(stream_id: str):
    return relay_manager.stats(stream_id)


async def validate_ingest_key(ingest_key: str, client_addr: str) -> bool:
    """Ask the main API whether this ingest key belongs to a live stream.

    Same validation the RTMP on_publish path uses, so the browser Capture
    Studio and hardware encoders share one trust model.
    """
    url = f"{get_settings().api_url.rstrip('/')}/v1/ingest/on-publish"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, data={"name": ingest_key, "addr": client_addr})
        return response.status_code < 300
    except httpx.HTTPError:
        logger.warning("could not reach the API to validate an ingest key")
        return False


@app.websocket("/capture/{stream_id}")
async def capture_websocket(websocket: WebSocket, stream_id: str):
    """Capture Studio gateway: browser MediaRecorder chunks in, RTMP out.

    Close codes: 4403 = missing/invalid ingest key, 1011 = encoder failure.
    """
    await websocket.accept()
    ingest_key = websocket.query_params.get("key", "")
    client_addr = websocket.client.host if websocket.client else "unknown"

    if not ingest_key or not await validate_ingest_key(ingest_key, client_addr):
        await websocket.close(code=4403)
        return

    publish_url = f"{get_settings().rtmp_publish_base_url.rstrip('/')}/{ingest_key}"
    stabilize = websocket.query_params.get("stabilize") == "1"
    try:
        handle = capture_manager.start(stream_id, publish_url, stabilize=stabilize)
    except FileNotFoundError:
        await websocket.close(code=1011)
        return

    await websocket.send_json({"type": "capture_started", "stream_id": stream_id})
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            chunk = message.get("bytes")
            if not chunk:
                continue
            try:
                await asyncio.to_thread(handle.feed, chunk)
            except (BrokenPipeError, OSError):
                logger.warning("capture encoder for %s died mid-stream", stream_id)
                await websocket.close(code=1011)
                break
    except WebSocketDisconnect:
        pass
    finally:
        capture_manager.stop(stream_id)
