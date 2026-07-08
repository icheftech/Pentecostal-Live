from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.limiter import limiter
from app.routers import auth, organizations, platform_keys, streams, tokens


settings = get_settings()

app = FastAPI(
    title="Pentecostal Live API",
    version="0.1.0",
    docs_url="/v1/docs",
    openapi_url="/v1/openapi.json",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/v1")
app.include_router(tokens.router, prefix="/v1")
app.include_router(organizations.router, prefix="/v1")
app.include_router(platform_keys.router, prefix="/v1")
app.include_router(streams.router, prefix="/v1")


@app.get("/health")
def health():
    return {"status": "ok", "service": "pentecostal-live-api"}


@app.websocket("/v1/ws/streams/{stream_id}")
async def stream_websocket(websocket: WebSocket, stream_id: str):
    await websocket.accept()
    await websocket.send_json(
        {
            "type": "connected",
            "stream_id": stream_id,
            "message": "Metrics transport ready for media-server integration",
        }
    )
    await websocket.close()
