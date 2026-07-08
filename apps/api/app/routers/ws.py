"""Authenticated websocket that pushes live stream metrics.

Auth design: browsers can't set headers on websocket handshakes, so the
client passes its JWT as a ``?token=`` query parameter. The token is decoded
with the same ``decode_access_token`` used by HTTP auth, the user/org/role
membership is loaded via ``resolve_context_from_token`` (shared with
``get_current_context``), and the stream must belong to the token's org.

Close codes (sent after ``accept()`` so browsers can observe them):
- 4401: missing/invalid token, or no active membership in the token's org
- 4404: stream not found in the token's org
"""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app import models
from app.db import SessionLocal
from app.deps import resolve_context_from_token
from app.services import stream_stats


router = APIRouter(tags=["websocket"])

WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_NOT_FOUND = 4404

# How often metrics are pushed to connected clients.
METRICS_PUSH_INTERVAL_SECONDS = 3.0


@router.websocket("/ws/streams/{stream_id}")
async def stream_websocket(websocket: WebSocket, stream_id: str):
    token = websocket.query_params.get("token")

    # Authenticate and org-scope before doing any work. The DB session is
    # only held for the handshake, not for the lifetime of the socket.
    stream = None
    context = None
    if token:
        with SessionLocal() as db:
            context = resolve_context_from_token(token, db)
            if context is not None:
                stream = db.scalar(
                    select(models.Stream)
                    .where(models.Stream.id == stream_id)
                    .where(models.Stream.organization_id == context.organization.id)
                )

    # Accept first so the custom close code reaches browser clients
    # (rejecting the handshake would surface as an opaque HTTP error).
    await websocket.accept()
    if context is None:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return
    if stream is None:
        await websocket.close(code=WS_CLOSE_NOT_FOUND)
        return

    # Push metrics until the client disconnects. A stream going offline is
    # NOT a disconnect condition: we keep pushing offline stats and let the
    # client decide what to do.
    try:
        while True:
            stats = await stream_stats.fetch_stream_stats(stream_id)
            await websocket.send_json(
                {
                    "type": "metrics",
                    **stats,
                    "health_status": stream_stats.derive_health(stats),
                }
            )
            # Sleep between pushes, but wake immediately if the client
            # disconnects (or sends anything) instead of blocking on sleep.
            try:
                message = await asyncio.wait_for(
                    websocket.receive(), timeout=METRICS_PUSH_INTERVAL_SECONDS
                )
                if message.get("type") == "websocket.disconnect":
                    break
            except asyncio.TimeoutError:
                continue
    except (WebSocketDisconnect, RuntimeError):
        # WebSocketDisconnect: client went away mid send/receive.
        # RuntimeError: starlette raises this if the socket is already closed.
        pass
