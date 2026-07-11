"""WebSocket connection manager — singleton for real-time push (Phase 4).

Tracks which users are connected to which leaderboard and provides
methods for targeted and broadcast message delivery.
"""

import logging
import json
import asyncio
from typing import Any

from fastapi import WebSocket

from backend.redis_client import redis_client

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

    async def publish_to_user(self, lb_id: str, user_id: str, message: dict[str, Any]) -> None:
        """Publish a message to a specific user via Redis Pub/Sub."""
        payload = {
            "target": "user",
            "lb_id": lb_id,
            "user_id": user_id,
            "message": message,
        }
        await redis_client.publish("liveboard:ws_events", json.dumps(payload))

    async def publish_to_leaderboard(self, lb_id: str, message: dict[str, Any]) -> None:
        """Publish a broadcast message to a leaderboard via Redis Pub/Sub."""
        payload = {
            "target": "leaderboard",
            "lb_id": lb_id,
            "message": message,
        }
        await redis_client.publish("liveboard:ws_events", json.dumps(payload))

    async def listen_pubsub(self) -> None:
        """Listen to Redis Pub/Sub and dispatch messages to local WebSockets."""
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("liveboard:ws_events")
        logger.info("Started Redis Pub/Sub listener for WebSockets.")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data_str = message["data"]
                    try:
                        data = json.loads(data_str)
                        target = data.get("target")
                        lb_id = data.get("lb_id")
                        msg = data.get("message")
                        
                        if target == "user":
                            uid = data.get("user_id")
                            if uid and lb_id and msg:
                                await self._send_to_user_local(lb_id, uid, msg)
                        elif target == "leaderboard":
                            if lb_id and msg:
                                await self._broadcast_to_leaderboard_local(lb_id, msg)
                    except json.JSONDecodeError:
                        logger.warning("Failed to decode Pub/Sub message: %s", data_str)
        except asyncio.CancelledError:
            logger.info("Pub/Sub listener cancelled.")
        except Exception as e:
            logger.error("Pub/Sub listener error: %s", e)
        finally:
            await pubsub.unsubscribe("liveboard:ws_events")
            await pubsub.close()

    async def _send_to_user_local(
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

    async def _broadcast_to_leaderboard_local(
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
