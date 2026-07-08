import hmac
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status

from media_server import schemas
from media_server.config import get_settings
from media_server.relay import RelayManager
from pentecostal_ffmpeg import Destination, build_destination_url, resolve_rtmp_url

settings = get_settings()
relay_manager = RelayManager(
    ffmpeg_binary=settings.ffmpeg_binary,
    hls_root=settings.hls_root,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
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
    for item in payload.destinations:
        rtmp_url = item.rtmp_url or resolve_rtmp_url(item.platform)
        if not rtmp_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown platform '{item.platform}' and no rtmp_url provided",
            )
        destinations.append(
            Destination(
                platform=item.platform,
                url=build_destination_url(rtmp_url, item.stream_key),
            )
        )

    if not destinations and not payload.hls:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Relay needs at least one destination or hls=true",
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
        ],
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
