"""WebSocket connection manager — singleton for real-time push (Phase 4).

Tracks which users are connected to which leaderboard and provides
methods for targeted and broadcast message delivery.
"""

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections per leaderboard.

    Structure: ``connections[lb_id][user_id] = WebSocket``

    All send methods are no-ops when the target user is not connected.
    Broken connections are silently removed to avoid broadcast errors.
    """

    def __init__(self) -> None:
        # lb_id -> {user_id -> WebSocket}
        self.connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, lb_id: str, user_id: str, ws: WebSocket) -> None:
        """Accept a WebSocket and register it for the given leaderboard + user."""
        await ws.accept()
        self.connections.setdefault(lb_id, {})[user_id] = ws

    async def disconnect(self, lb_id: str, user_id: str) -> None:
        """Remove a user's connection. Cleans up empty leaderboard dicts."""
        lb_conns = self.connections.get(lb_id)
        if lb_conns:
            lb_conns.pop(user_id, None)
            if not lb_conns:
                del self.connections[lb_id]

    async def send_to_user(
        self, lb_id: str, user_id: str, message: dict[str, Any]
    ) -> None:
        """Send a JSON message to a specific user on a leaderboard.

        No-op if the user is not connected. Silently removes broken connections.
        """
        ws = self.connections.get(lb_id, {}).get(user_id)
        if ws is None:
            return
        try:
            await ws.send_json(message)
        except Exception:
            logger.warning(
                "Failed to send to user %s on lb %s — removing connection",
                user_id,
                lb_id,
            )
            await self.disconnect(lb_id, user_id)

    async def broadcast_to_leaderboard(
        self, lb_id: str, message: dict[str, Any]
    ) -> None:
        """Broadcast a JSON message to all users connected to a leaderboard.

        Broken connections are silently cleaned up.
        """
        lb_conns = self.connections.get(lb_id)
        if not lb_conns:
            return

        dead: list[str] = []
        for user_id, ws in lb_conns.items():
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning(
                    "Broadcast failed for user %s on lb %s — will remove",
                    user_id,
                    lb_id,
                )
                dead.append(user_id)

        for uid in dead:
            lb_conns.pop(uid, None)
        if not lb_conns:
            self.connections.pop(lb_id, None)

    def connected_count(self, lb_id: str) -> int:
        """Return the number of users connected to a leaderboard."""
        return len(self.connections.get(lb_id, {}))

    def is_connected(self, lb_id: str, user_id: str) -> bool:
        """Check if a specific user is connected to a leaderboard."""
        return user_id in self.connections.get(lb_id, {})


# ── Singleton instance ────────────────────────────────────────
manager = ConnectionManager()
