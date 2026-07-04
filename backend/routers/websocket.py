"""WebSocket endpoint — Phase 4: Real-time leaderboard push.

Clients connect via ``/ws/{lb_id}/{user_id}`` to receive live rank change
notifications, top-10 broadcasts, and displacement alerts.
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.connection_manager import manager
from backend.redis_client import redis_client
from backend.routers.scores import extract_actual_score

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{lb_id}/{user_id}")
async def leaderboard_ws(websocket: WebSocket, lb_id: str, user_id: str):
    """WebSocket endpoint for real-time leaderboard updates.

    On connect:
    1. Registers the user in the ConnectionManager.
    2. Sends the user's current rank and score as the first message.

    The connection is kept alive until the client disconnects.
    All push messages (rank_change, leaderboard_update, displaced) are
    initiated server-side by score update events in the scores router.
    """
    await manager.connect(lb_id, user_id, websocket)
    logger.info("WS connected: lb=%s user=%s", lb_id, user_id)

    try:
        # ── Send current rank as the first message ────────────
        redis_key = f"lb:{lb_id}:all"
        pipe = redis_client.pipeline(transaction=True)
        pipe.zrevrank(redis_key, user_id)
        pipe.zscore(redis_key, user_id)
        rank_0, composite = await pipe.execute()

        if rank_0 is not None:
            await websocket.send_json({
                "type": "current_rank",
                "user_id": user_id,
                "rank": rank_0 + 1,
                "score": extract_actual_score(composite),
            })
        else:
            await websocket.send_json({
                "type": "current_rank",
                "user_id": user_id,
                "rank": None,
                "score": 0,
            })

        # ── Keep connection alive ─────────────────────────────
        # All pushes are server-initiated via ConnectionManager.
        # We await client messages to detect disconnection;
        # clients can send pings or any keepalive data.
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "ack", "data": data})

    except WebSocketDisconnect:
        logger.info("WS disconnected: lb=%s user=%s", lb_id, user_id)
    except Exception as exc:
        logger.warning("WS error: lb=%s user=%s error=%s", lb_id, user_id, exc)
    finally:
        await manager.disconnect(lb_id, user_id)
