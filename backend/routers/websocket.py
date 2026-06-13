"""WebSocket connection handler — placeholder for Phase 2+."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()


@router.websocket("/ws/leaderboard/{leaderboard_id}")
async def leaderboard_ws(websocket: WebSocket, leaderboard_id: str):
    """WebSocket endpoint for real-time leaderboard updates.

    Clients connect here to receive live score changes.
    Full implementation in Phase 2.
    """
    await manager.connect(websocket)
    try:
        while True:
            # keep connection alive; real logic comes in Phase 2
            data = await websocket.receive_text()
            await websocket.send_json({"echo": data, "leaderboard_id": leaderboard_id})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
