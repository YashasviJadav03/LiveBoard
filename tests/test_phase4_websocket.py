"""Tests for LiveBoard Phase 4 — WebSocket Real-Time Push.

Covers:
- ConnectionManager: connect, disconnect, send_to_user, broadcast
- Score update WS push: rank_change, leaderboard_update, displaced
- No rank_change when rank doesn't change
- No rank_change for first-time score (no previous rank)
- Disconnected / broken clients cleaned up gracefully
- Full multi-user scenario
"""

import pytest
from httpx import AsyncClient

from backend.connection_manager import ConnectionManager, manager


# ── Mock WebSocket ────────────────────────────────────────────

class MockWebSocket:
    """A mock WebSocket that captures sent messages."""

    def __init__(self):
        self.messages: list[dict] = []
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, data: dict):
        self.messages.append(data)

    def get_messages_by_type(self, msg_type: str) -> list[dict]:
        """Filter captured messages by their ``type`` field."""
        return [m for m in self.messages if m.get("type") == msg_type]


class BrokenWebSocket:
    """A mock WebSocket that raises on send_json (simulates disconnection)."""

    async def accept(self):
        pass

    async def send_json(self, data: dict):
        raise RuntimeError("Connection closed")


# ── Helpers ───────────────────────────────────────────────────

async def create_user(
    client: AsyncClient, username: str, display_name: str = None, region: str = None
) -> str:
    body = {"username": username}
    if display_name:
        body["display_name"] = display_name
    if region:
        body["region"] = region
    resp = await client.post("/users", json=body)
    assert resp.status_code == 201, f"Failed to create user {username}: {resp.text}"
    return resp.json()["id"]


async def create_leaderboard(client: AsyncClient, lb_id: str) -> dict:
    resp = await client.post("/leaderboards", json={
        "id": lb_id,
        "name": f"Test LB {lb_id}",
    })
    assert resp.status_code == 201, f"Failed to create leaderboard {lb_id}: {resp.text}"
    return resp.json()


async def submit_score(client: AsyncClient, lb_id: str, user_id: str, delta: float) -> dict:
    resp = await client.post(f"/leaderboards/{lb_id}/scores", json={
        "user_id": user_id,
        "delta": delta,
    })
    assert resp.status_code == 201, f"Score submit failed: {resp.text}"
    return resp.json()


async def add_friendship(client: AsyncClient, user_id: str, friend_id: str):
    resp = await client.post(f"/users/{user_id}/friends/{friend_id}")
    assert resp.status_code == 201, f"Friendship failed: {resp.text}"


def register_mock_ws(lb_id: str, user_id: str) -> MockWebSocket:
    """Register a MockWebSocket directly on the singleton manager."""
    ws = MockWebSocket()
    manager.connections.setdefault(lb_id, {})[user_id] = ws
    return ws


# ══════════════════════════════════════════════════════════════
# 1. ConnectionManager unit tests
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_cm_connect_registers_connection():
    cm = ConnectionManager()
    ws = MockWebSocket()
    await cm.connect("lb1", "user1", ws)

    assert ws.accepted
    assert cm.is_connected("lb1", "user1")
    assert cm.connected_count("lb1") == 1


@pytest.mark.asyncio
async def test_cm_disconnect_removes_connection():
    cm = ConnectionManager()
    ws = MockWebSocket()
    await cm.connect("lb1", "user1", ws)
    await cm.disconnect("lb1", "user1")

    assert not cm.is_connected("lb1", "user1")
    assert cm.connected_count("lb1") == 0
    # Empty leaderboard dict should be cleaned up
    assert "lb1" not in cm.connections


@pytest.mark.asyncio
async def test_cm_disconnect_nonexistent_is_noop():
    """Disconnecting a non-existent user/lb should not raise."""
    cm = ConnectionManager()
    await cm.disconnect("lb1", "user1")  # no-op


@pytest.mark.asyncio
async def test_cm_send_to_user_delivers():
    cm = ConnectionManager()
    ws = MockWebSocket()
    await cm.connect("lb1", "user1", ws)
    await cm.send_to_user("lb1", "user1", {"type": "test", "data": 42})

    assert len(ws.messages) == 1
    assert ws.messages[0] == {"type": "test", "data": 42}


@pytest.mark.asyncio
async def test_cm_send_to_user_noop_if_not_connected():
    """Sending to a user who is not connected should not raise."""
    cm = ConnectionManager()
    await cm.send_to_user("lb1", "ghost_user", {"type": "test"})


@pytest.mark.asyncio
async def test_cm_send_to_user_removes_broken():
    cm = ConnectionManager()
    ws = BrokenWebSocket()
    # Manually register (bypassing accept) to simulate a connection that broke
    cm.connections.setdefault("lb1", {})["user1"] = ws

    await cm.send_to_user("lb1", "user1", {"type": "test"})

    assert not cm.is_connected("lb1", "user1")


@pytest.mark.asyncio
async def test_cm_broadcast_delivers_to_all():
    cm = ConnectionManager()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    await cm.connect("lb1", "user1", ws1)
    await cm.connect("lb1", "user2", ws2)

    await cm.broadcast_to_leaderboard("lb1", {"type": "update"})

    assert len(ws1.messages) == 1
    assert len(ws2.messages) == 1
    assert ws1.messages[0] == {"type": "update"}
    assert ws2.messages[0] == {"type": "update"}


@pytest.mark.asyncio
async def test_cm_broadcast_removes_broken_keeps_good():
    cm = ConnectionManager()
    ws_good = MockWebSocket()
    ws_broken = BrokenWebSocket()
    await cm.connect("lb1", "user1", ws_good)
    cm.connections["lb1"]["user2"] = ws_broken

    await cm.broadcast_to_leaderboard("lb1", {"type": "update"})

    assert len(ws_good.messages) == 1
    assert not cm.is_connected("lb1", "user2")
    assert cm.is_connected("lb1", "user1")


@pytest.mark.asyncio
async def test_cm_broadcast_noop_empty_leaderboard():
    """Broadcast to a leaderboard with no connections should not raise."""
    cm = ConnectionManager()
    await cm.broadcast_to_leaderboard("nonexistent", {"type": "update"})


@pytest.mark.asyncio
async def test_cm_multiple_leaderboards():
    cm = ConnectionManager()
    ws_a = MockWebSocket()
    ws_b = MockWebSocket()
    await cm.connect("lb_a", "user1", ws_a)
    await cm.connect("lb_b", "user1", ws_b)

    await cm.broadcast_to_leaderboard("lb_a", {"type": "msg_a"})

    # Only ws_a should receive (lb_a broadcast)
    assert len(ws_a.messages) == 1
    assert ws_a.messages[0]["type"] == "msg_a"
    assert len(ws_b.messages) == 0


# ══════════════════════════════════════════════════════════════
# 2. Rank change notification via WS push
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rank_change_notification_sent(client: AsyncClient):
    """When a user overtakes another, they receive a rank_change notification."""
    u1 = await create_user(client, "p4_rc_u1", region="US")
    u2 = await create_user(client, "p4_rc_u2", region="US")
    await create_leaderboard(client, "p4_rc_lb")

    # Establish initial ranks
    await submit_score(client, "p4_rc_lb", u1, 200.0)  # rank 1
    await submit_score(client, "p4_rc_lb", u2, 100.0)  # rank 2

    # Connect mock WS for u2
    ws_u2 = register_mock_ws("p4_rc_lb", u2)

    # u2 overtakes u1
    await submit_score(client, "p4_rc_lb", u2, 200.0)  # total 300, now rank 1

    # Check rank_change was sent to u2
    rc_msgs = ws_u2.get_messages_by_type("rank_change")
    assert len(rc_msgs) == 1
    msg = rc_msgs[0]
    assert msg["previous_rank"] == 2
    assert msg["new_rank"] == 1
    assert msg["score"] == 300
    assert msg["user_id"] == u2
    assert "You moved from #2 to #1" in msg["message"]
    assert "\U0001f389" in msg["message"]


@pytest.mark.asyncio
async def test_rank_change_correct_numbers_multi_rank_jump(client: AsyncClient):
    """Rank change message has correct numbers for a multi-rank jump."""
    users = []
    await create_leaderboard(client, "p4_jump_lb")

    # Create 5 users with descending scores
    for i in range(5):
        uid = await create_user(client, f"p4_jump_u{i}", region="US")
        users.append(uid)
        await submit_score(client, "p4_jump_lb", uid, (5 - i) * 100.0)

    # users[0]=500 (rank 1), users[1]=400 (rank 2), ... users[4]=100 (rank 5)

    ws_u4 = register_mock_ws("p4_jump_lb", users[4])

    # users[4] jumps from rank 5 to rank 1 with a big score
    await submit_score(client, "p4_jump_lb", users[4], 600.0)  # total 700

    rc_msgs = ws_u4.get_messages_by_type("rank_change")
    assert len(rc_msgs) == 1
    assert rc_msgs[0]["previous_rank"] == 5
    assert rc_msgs[0]["new_rank"] == 1
    assert "You moved from #5 to #1" in rc_msgs[0]["message"]


@pytest.mark.asyncio
async def test_no_rank_change_when_same_position(client: AsyncClient):
    """If score updated but rank doesn't change, no rank_change message."""
    u1 = await create_user(client, "p4_norc_u1", region="US")
    await create_leaderboard(client, "p4_norc_lb")

    await submit_score(client, "p4_norc_lb", u1, 100.0)

    ws_u1 = register_mock_ws("p4_norc_lb", u1)

    # Update score — still rank 1 (only user)
    await submit_score(client, "p4_norc_lb", u1, 50.0)

    rc_msgs = ws_u1.get_messages_by_type("rank_change")
    assert len(rc_msgs) == 0


@pytest.mark.asyncio
async def test_no_rank_change_for_first_score(client: AsyncClient):
    """First score submission (no previous rank) should NOT send rank_change."""
    u1 = await create_user(client, "p4_first_u1", region="US")
    await create_leaderboard(client, "p4_first_lb")

    ws_u1 = register_mock_ws("p4_first_lb", u1)

    await submit_score(client, "p4_first_lb", u1, 100.0)

    rc_msgs = ws_u1.get_messages_by_type("rank_change")
    assert len(rc_msgs) == 0


# ══════════════════════════════════════════════════════════════
# 3. Top-10 leaderboard broadcast
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_leaderboard_update_broadcast_top10(client: AsyncClient):
    """When a score update puts the user in top 10, broadcast to all viewers."""
    u1 = await create_user(client, "p4_t10_u1", region="US")
    u2 = await create_user(client, "p4_t10_u2", region="US")
    await create_leaderboard(client, "p4_t10_lb")

    await submit_score(client, "p4_t10_lb", u1, 200.0)
    await submit_score(client, "p4_t10_lb", u2, 100.0)

    ws_u1 = register_mock_ws("p4_t10_lb", u1)
    ws_u2 = register_mock_ws("p4_t10_lb", u2)

    # u2 gets more points — still in top 10 (rank 2 → rank 2)
    await submit_score(client, "p4_t10_lb", u2, 50.0)

    # Both should receive leaderboard_update broadcast
    lu_u1 = ws_u1.get_messages_by_type("leaderboard_update")
    lu_u2 = ws_u2.get_messages_by_type("leaderboard_update")
    assert len(lu_u1) >= 1
    assert len(lu_u2) >= 1

    msg = lu_u1[0]
    assert msg["lb_id"] == "p4_t10_lb"
    assert msg["segment"] == "all_time"
    assert isinstance(msg["top10"], list)
    assert len(msg["top10"]) == 2  # only 2 users total


@pytest.mark.asyncio
async def test_leaderboard_update_includes_correct_scores(client: AsyncClient):
    """Top-10 broadcast entries should have correct rank, user_id, and score."""
    u1 = await create_user(client, "p4_t10s_u1", region="US")
    u2 = await create_user(client, "p4_t10s_u2", region="US")
    await create_leaderboard(client, "p4_t10s_lb")

    await submit_score(client, "p4_t10s_lb", u1, 200.0)  # rank 1

    ws_u1 = register_mock_ws("p4_t10s_lb", u1)

    await submit_score(client, "p4_t10s_lb", u2, 300.0)  # rank 1, pushes u1 to rank 2

    lu_msgs = ws_u1.get_messages_by_type("leaderboard_update")
    assert len(lu_msgs) >= 1

    top10 = lu_msgs[0]["top10"]
    assert top10[0]["rank"] == 1
    assert top10[0]["user_id"] == u2
    assert top10[0]["score"] == 300
    assert top10[1]["rank"] == 2
    assert top10[1]["user_id"] == u1
    assert top10[1]["score"] == 200


# ══════════════════════════════════════════════════════════════
# 4. Displacement notification
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_displacement_notification(client: AsyncClient):
    """User displaced from their rank receives a displacement notification."""
    u1 = await create_user(client, "p4_disp_u1", region="US")
    u2 = await create_user(client, "p4_disp_u2", region="US")
    await create_leaderboard(client, "p4_disp_lb")

    await submit_score(client, "p4_disp_lb", u1, 200.0)  # rank 1
    await submit_score(client, "p4_disp_lb", u2, 100.0)  # rank 2

    ws_u1 = register_mock_ws("p4_disp_lb", u1)
    ws_u2 = register_mock_ws("p4_disp_lb", u2)

    # u2 overtakes u1 (u1 gets displaced from rank 1 to rank 2)
    await submit_score(client, "p4_disp_lb", u2, 200.0)  # total 300, now rank 1

    disp_msgs = ws_u1.get_messages_by_type("displaced")
    assert len(disp_msgs) == 1
    msg = disp_msgs[0]
    assert msg["previous_rank"] == 1
    assert msg["new_rank"] == 2
    assert msg["displaced_by"] == "p4_disp_u2"


@pytest.mark.asyncio
async def test_no_displacement_when_rank_unchanged(client: AsyncClient):
    """When the scoring user stays at the same rank, no displacement sent."""
    u1 = await create_user(client, "p4_nodsp_u1", region="US")
    u2 = await create_user(client, "p4_nodsp_u2", region="US")
    await create_leaderboard(client, "p4_nodsp_lb")

    await submit_score(client, "p4_nodsp_lb", u1, 200.0)  # rank 1
    await submit_score(client, "p4_nodsp_lb", u2, 100.0)  # rank 2

    ws_u1 = register_mock_ws("p4_nodsp_lb", u1)
    ws_u2 = register_mock_ws("p4_nodsp_lb", u2)

    # u2 adds points but NOT enough to overtake (still rank 2)
    await submit_score(client, "p4_nodsp_lb", u2, 50.0)  # total 150, still rank 2

    disp_u1 = ws_u1.get_messages_by_type("displaced")
    disp_u2 = ws_u2.get_messages_by_type("displaced")
    assert len(disp_u1) == 0
    assert len(disp_u2) == 0


@pytest.mark.asyncio
async def test_displacement_includes_username(client: AsyncClient):
    """Displacement notification shows the displacer's username."""
    u1 = await create_user(client, "p4_dname_alice", region="US")
    u2 = await create_user(client, "p4_dname_bob", region="US")
    await create_leaderboard(client, "p4_dname_lb")

    await submit_score(client, "p4_dname_lb", u1, 200.0)

    ws_u1 = register_mock_ws("p4_dname_lb", u1)

    await submit_score(client, "p4_dname_lb", u2, 300.0)

    disp = ws_u1.get_messages_by_type("displaced")
    assert len(disp) == 1
    assert disp[0]["displaced_by"] == "p4_dname_bob"


# ══════════════════════════════════════════════════════════════
# 5. Disconnected clients handled gracefully
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_broken_connection_removed_on_push(client: AsyncClient):
    """Broken connections should be cleaned up, not cause errors."""
    u1 = await create_user(client, "p4_brk_u1", region="US")
    await create_leaderboard(client, "p4_brk_lb")

    await submit_score(client, "p4_brk_lb", u1, 100.0)

    # Register a broken WebSocket
    ws_broken = BrokenWebSocket()
    manager.connections.setdefault("p4_brk_lb", {})[u1] = ws_broken

    # Score update should NOT raise even though WS is broken
    result = await submit_score(client, "p4_brk_lb", u1, 50.0)
    assert result["new_rank"] == 1  # score update still works

    # Connection should have been cleaned up
    assert not manager.is_connected("p4_brk_lb", u1)


@pytest.mark.asyncio
async def test_no_error_when_no_connections(client: AsyncClient):
    """Score updates with no WS connections should work fine."""
    u1 = await create_user(client, "p4_nc_u1", region="US")
    await create_leaderboard(client, "p4_nc_lb")

    # No WS connections registered
    result = await submit_score(client, "p4_nc_lb", u1, 100.0)
    assert result["new_rank"] == 1
    assert result["new_score"] == 100


@pytest.mark.asyncio
async def test_push_only_reaches_correct_leaderboard(client: AsyncClient):
    """WS push should only go to connections on the same leaderboard."""
    u1 = await create_user(client, "p4_iso_u1", region="US")
    await create_leaderboard(client, "p4_iso_lb_a")
    await create_leaderboard(client, "p4_iso_lb_b")

    await submit_score(client, "p4_iso_lb_a", u1, 100.0)

    # Connect u1 to lb_b (NOT lb_a)
    ws_u1_b = register_mock_ws("p4_iso_lb_b", u1)

    # Score update on lb_a should NOT push to lb_b connection
    await submit_score(client, "p4_iso_lb_a", u1, 50.0)

    assert len(ws_u1_b.messages) == 0


# ══════════════════════════════════════════════════════════════
# 6. Full multi-user scenario
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_full_scenario_three_users(client: AsyncClient):
    """Full scenario: 3 users, score updates, verify all notification types."""
    u1 = await create_user(client, "p4_full_alice", region="US")
    u2 = await create_user(client, "p4_full_bob", region="US")
    u3 = await create_user(client, "p4_full_charlie", region="US")
    await create_leaderboard(client, "p4_full_lb")

    # Establish ranks: u1=300 (rank 1), u2=200 (rank 2), u3=100 (rank 3)
    await submit_score(client, "p4_full_lb", u1, 300.0)
    await submit_score(client, "p4_full_lb", u2, 200.0)
    await submit_score(client, "p4_full_lb", u3, 100.0)

    # Connect all 3 via mock WebSockets
    ws1 = register_mock_ws("p4_full_lb", u1)
    ws2 = register_mock_ws("p4_full_lb", u2)
    ws3 = register_mock_ws("p4_full_lb", u3)

    # u3 scores big — goes from rank 3 to rank 1 (total 500)
    await submit_score(client, "p4_full_lb", u3, 400.0)

    # ── u3 should get rank_change (3 → 1) ────────────────────
    rc = ws3.get_messages_by_type("rank_change")
    assert len(rc) == 1
    assert rc[0]["previous_rank"] == 3
    assert rc[0]["new_rank"] == 1
    assert rc[0]["score"] == 500

    # ── u1 was at rank 1, now displaced to rank 2 ────────────
    disp = ws1.get_messages_by_type("displaced")
    assert len(disp) == 1
    assert disp[0]["previous_rank"] == 1
    assert disp[0]["new_rank"] == 2
    assert disp[0]["displaced_by"] == "p4_full_charlie"

    # ── All 3 should get leaderboard_update (u3 in top 10) ───
    for ws in [ws1, ws2, ws3]:
        lu = ws.get_messages_by_type("leaderboard_update")
        assert len(lu) >= 1
        assert lu[0]["lb_id"] == "p4_full_lb"
        assert lu[0]["segment"] == "all_time"
        assert len(lu[0]["top10"]) == 3

    # ── u2 should NOT get displaced (only rank 1 holder is notified) ─
    disp_u2 = ws2.get_messages_by_type("displaced")
    assert len(disp_u2) == 0


@pytest.mark.asyncio
async def test_two_consecutive_updates_both_push(client: AsyncClient):
    """Two rapid score updates should each trigger correct WS pushes."""
    u1 = await create_user(client, "p4_consec_u1", region="US")
    u2 = await create_user(client, "p4_consec_u2", region="US")
    await create_leaderboard(client, "p4_consec_lb")

    await submit_score(client, "p4_consec_lb", u1, 100.0)  # rank 1
    await submit_score(client, "p4_consec_lb", u2, 50.0)   # rank 2

    ws_u1 = register_mock_ws("p4_consec_lb", u1)
    ws_u2 = register_mock_ws("p4_consec_lb", u2)

    # First update: u2 overtakes u1
    await submit_score(client, "p4_consec_lb", u2, 100.0)  # total 150, rank 1

    # Second update: u1 overtakes u2 back
    await submit_score(client, "p4_consec_lb", u1, 100.0)  # total 200, rank 1

    # u1 should have: displaced (from first update) + rank_change (from second)
    disp_u1 = ws_u1.get_messages_by_type("displaced")
    rc_u1 = ws_u1.get_messages_by_type("rank_change")
    assert len(disp_u1) == 1  # displaced when u2 overtook
    assert len(rc_u1) == 1    # rank changed when u1 took rank 1 back
    assert rc_u1[0]["previous_rank"] == 2
    assert rc_u1[0]["new_rank"] == 1

    # u2 should have: rank_change (from first update) + displaced (from second)
    rc_u2 = ws_u2.get_messages_by_type("rank_change")
    disp_u2 = ws_u2.get_messages_by_type("displaced")
    assert len(rc_u2) == 1
    assert rc_u2[0]["previous_rank"] == 2
    assert rc_u2[0]["new_rank"] == 1
    assert len(disp_u2) == 1  # displaced when u1 took rank 1 back
