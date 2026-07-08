"""Tests for LiveBoard Phase 2 — Core Ranking Engine.

Covers:
- POST /leaderboards (create)
- POST /leaderboards/{lb_id}/scores (score update with Redis + tie-breaking)
- GET /leaderboards/{lb_id}/rank/{user_id} (rank + surrounding)
- GET /leaderboards/{lb_id}/top (paginated top-N)
- Tie-breaking: earlier achiever ranks higher on equal scores
- score_events table audit trail
"""

import asyncio
import time

import pytest
from httpx import AsyncClient
from sqlalchemy import select, func

from backend.models.user import ScoreEvent
from tests.conftest import TestSession


# ── Helpers ───────────────────────────────────────────────────

async def create_user(client: AsyncClient, username: str, display_name: str = None) -> str:
    """Create a user and return their ID."""
    body = {"username": username}
    if display_name:
        body["display_name"] = display_name
    resp = await client.post("/users", json=body)
    assert resp.status_code == 201, f"Failed to create user {username}: {resp.text}"
    return resp.json()["id"]


async def create_leaderboard(client: AsyncClient, lb_id: str, name: str = None) -> dict:
    """Create a leaderboard and return its metadata."""
    resp = await client.post("/leaderboards", json={
        "id": lb_id,
        "name": name or f"Test LB {lb_id}",
        "description": f"Test leaderboard {lb_id}",
    })
    assert resp.status_code == 201, f"Failed to create leaderboard {lb_id}: {resp.text}"
    return resp.json()


async def submit_score(client: AsyncClient, lb_id: str, user_id: str, delta: float) -> dict:
    """Submit a score delta and return the response."""
    resp = await client.post(f"/leaderboards/{lb_id}/scores", json={
        "user_id": user_id,
        "delta": delta,
    })
    assert resp.status_code == 201, f"Score submit failed: {resp.text}"
    return resp.json()


# ──────────────────────────────────────────────────────────────
# 1. POST /leaderboards — Create Leaderboard
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_leaderboard(client: AsyncClient):
    resp = await client.post("/leaderboards", json={
        "id": "test_game_1",
        "name": "Game One Rankings",
        "description": "Weekly challenge board",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "test_game_1"
    assert data["name"] == "Game One Rankings"
    assert data["description"] == "Weekly challenge board"
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_duplicate_leaderboard(client: AsyncClient):
    await create_leaderboard(client, "test_dup_lb")
    resp = await client.post("/leaderboards", json={
        "id": "test_dup_lb",
        "name": "Duplicate",
    })
    assert resp.status_code == 409


# ──────────────────────────────────────────────────────────────
# 2. POST /leaderboards/{lb_id}/scores — Score Update
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_update_returns_rank(client: AsyncClient):
    user_id = await create_user(client, "scorer1")
    await create_leaderboard(client, "test_score_lb")

    result = await submit_score(client, "test_score_lb", user_id, 100.0)

    assert result["user_id"] == user_id
    assert result["new_score"] == 100
    assert result["new_rank"] == 1
    assert result["previous_rank"] is None  # first submission


@pytest.mark.asyncio
async def test_score_update_incremental(client: AsyncClient):
    user_id = await create_user(client, "scorer2")
    await create_leaderboard(client, "test_incr_lb")

    r1 = await submit_score(client, "test_incr_lb", user_id, 50.0)
    assert r1["new_score"] == 50

    r2 = await submit_score(client, "test_incr_lb", user_id, 30.0)
    assert r2["new_score"] == 80
    assert r2["previous_rank"] == 1
    assert r2["new_rank"] == 1


@pytest.mark.asyncio
async def test_score_update_nonexistent_user(client: AsyncClient):
    await create_leaderboard(client, "test_nouser_lb")
    resp = await client.post("/leaderboards/test_nouser_lb/scores", json={
        "user_id": "00000000-0000-0000-0000-000000000000",
        "delta": 10.0,
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_score_update_nonexistent_leaderboard(client: AsyncClient):
    user_id = await create_user(client, "scorer_no_lb")
    resp = await client.post("/leaderboards/nonexistent_lb/scores", json={
        "user_id": user_id,
        "delta": 10.0,
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rank_changes_with_multiple_users(client: AsyncClient):
    u1 = await create_user(client, "rank_user1")
    u2 = await create_user(client, "rank_user2")
    u3 = await create_user(client, "rank_user3")
    await create_leaderboard(client, "test_rank_lb")

    # u1 gets 100, u2 gets 200, u3 gets 150
    await submit_score(client, "test_rank_lb", u1, 100.0)
    await submit_score(client, "test_rank_lb", u2, 200.0)
    await submit_score(client, "test_rank_lb", u3, 150.0)

    # u2 (200) should be rank 1, u3 (150) rank 2, u1 (100) rank 3
    # Now u1 adds 200 → total 300 → should jump to rank 1
    r = await submit_score(client, "test_rank_lb", u1, 200.0)
    assert r["new_score"] == 300
    assert r["new_rank"] == 1
    assert r["previous_rank"] == 3
    assert r["rank_change"] == 2  # moved up 2 positions


# ──────────────────────────────────────────────────────────────
# 3. Tie-breaking — earlier achiever ranks higher
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tiebreak_earlier_achiever_wins(client: AsyncClient):
    """Two users with identical scores — first achiever should rank higher."""
    u_early = await create_user(client, "early_bird")
    u_late = await create_user(client, "late_comer")
    await create_leaderboard(client, "test_tie_lb")

    # Early bird submits first
    r_early = await submit_score(client, "test_tie_lb", u_early, 1000.0)
    # Small delay to ensure different timestamp
    await asyncio.sleep(0.05)
    r_late = await submit_score(client, "test_tie_lb", u_late, 1000.0)

    # Early bird should have better (lower number) rank
    assert r_early["new_rank"] == 1
    assert r_late["new_rank"] == 2
    assert r_early["new_score"] == r_late["new_score"]  # same actual score


# ──────────────────────────────────────────────────────────────
# 4. GET /leaderboards/{lb_id}/rank/{user_id} — Rank + Surrounding
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_rank_with_surrounding(client: AsyncClient):
    """Rank query returns user info and ±3 surrounding users."""
    await create_leaderboard(client, "test_surround_lb")
    users = []
    for i in range(1, 8):  # 7 users
        uid = await create_user(client, f"surround_user{i}")
        users.append(uid)
        await submit_score(client, "test_surround_lb", uid, i * 100.0)

    # User 4 (score 400) should be rank 4 (from bottom of 7)
    # With 7 users scored 100..700: rank 1=u7(700), rank 2=u6(600), ..., rank 7=u1(100)
    # User 4 has score 400 → rank 4
    target = users[3]  # index 3 = 4th user, score 400

    resp = await client.get(f"/leaderboards/test_surround_lb/rank/{target}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["rank"] == 4
    assert data["score"] == 400
    assert data["username"] == "surround_user4"

    # Should have 3 above (ranks 1,2,3) and 3 below (ranks 5,6,7)
    surrounding = data["surrounding"]
    assert len(surrounding) == 6

    surrounding_ranks = [s["rank"] for s in surrounding]
    assert 1 in surrounding_ranks
    assert 2 in surrounding_ranks
    assert 3 in surrounding_ranks
    assert 5 in surrounding_ranks
    assert 6 in surrounding_ranks
    assert 7 in surrounding_ranks


@pytest.mark.asyncio
async def test_get_rank_top_user_fewer_above(client: AsyncClient):
    """Top-ranked user should have 0 above and up to 3 below."""
    await create_leaderboard(client, "test_top_rank_lb")
    users = []
    for i in range(1, 5):
        uid = await create_user(client, f"toprank_user{i}")
        users.append(uid)
        await submit_score(client, "test_top_rank_lb", uid, i * 100.0)

    # User 4 is rank 1 (highest score 400)
    resp = await client.get(f"/leaderboards/test_top_rank_lb/rank/{users[3]}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rank"] == 1
    # Should have 3 below (no one above)
    surrounding = data["surrounding"]
    assert len(surrounding) == 3
    for s in surrounding:
        assert s["rank"] > 1


@pytest.mark.asyncio
async def test_get_rank_not_on_leaderboard(client: AsyncClient):
    uid = await create_user(client, "not_on_lb")
    await create_leaderboard(client, "test_notfound_lb")

    resp = await client.get(f"/leaderboards/test_notfound_lb/rank/{uid}")
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────────
# 5. GET /leaderboards/{lb_id}/top — Paginated Top-N
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_top_leaderboard_basic(client: AsyncClient):
    await create_leaderboard(client, "test_top_lb")
    users = []
    for i in range(1, 6):
        uid = await create_user(client, f"top_user{i}")
        users.append(uid)
        await submit_score(client, "test_top_lb", uid, i * 50.0)

    resp = await client.get("/leaderboards/test_top_lb/top?limit=3&page=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_users"] == 5
    assert data["page"] == 1
    assert data["limit"] == 3
    assert len(data["entries"]) == 3

    # Entries should be in descending score order
    scores = [e["score"] for e in data["entries"]]
    assert scores == sorted(scores, reverse=True)

    # Rank numbers should be 1, 2, 3
    ranks = [e["rank"] for e in data["entries"]]
    assert ranks == [1, 2, 3]


@pytest.mark.asyncio
async def test_top_leaderboard_pagination(client: AsyncClient):
    """Page 2 should return different users than page 1."""
    await create_leaderboard(client, "test_page_lb")
    all_users = []
    for i in range(1, 11):  # 10 users
        uid = await create_user(client, f"page_user{i}")
        all_users.append(uid)
        await submit_score(client, "test_page_lb", uid, i * 10.0)

    page1 = await client.get("/leaderboards/test_page_lb/top?limit=5&page=1")
    page2 = await client.get("/leaderboards/test_page_lb/top?limit=5&page=2")

    p1_data = page1.json()
    p2_data = page2.json()

    # Page 1: ranks 1-5, Page 2: ranks 6-10
    assert len(p1_data["entries"]) == 5
    assert len(p2_data["entries"]) == 5
    assert p1_data["entries"][0]["rank"] == 1
    assert p2_data["entries"][0]["rank"] == 6

    # No overlap in user IDs between pages
    p1_ids = {e["user_id"] for e in p1_data["entries"]}
    p2_ids = {e["user_id"] for e in p2_data["entries"]}
    assert p1_ids.isdisjoint(p2_ids)


@pytest.mark.asyncio
async def test_top_leaderboard_returns_usernames(client: AsyncClient):
    """Top endpoint should resolve and return usernames from PostgreSQL."""
    await create_leaderboard(client, "test_uname_lb")
    uid = await create_user(client, "named_user", display_name="Named Guy")
    await submit_score(client, "test_uname_lb", uid, 500.0)

    resp = await client.get("/leaderboards/test_uname_lb/top?limit=10&page=1")
    data = resp.json()
    assert len(data["entries"]) == 1
    assert data["entries"][0]["username"] == "named_user"
    assert data["entries"][0]["user_id"] == uid


# ──────────────────────────────────────────────────────────────
# 6. score_events table audit trail
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_events_recorded(client: AsyncClient):
    """Every score update should create a row in score_events."""
    uid = await create_user(client, "audit_user")
    await create_leaderboard(client, "test_audit_lb")

    # Submit 3 score updates
    await submit_score(client, "test_audit_lb", uid, 10.0)
    await submit_score(client, "test_audit_lb", uid, 20.0)
    await submit_score(client, "test_audit_lb", uid, 30.0)

    # Query score_events table directly
    async with TestSession() as session:
        result = await session.execute(
            select(func.count()).where(
                ScoreEvent.leaderboard_id == "test_audit_lb"
            )
        )
        count = result.scalar_one()
        assert count == 3


# ──────────────────────────────────────────────────────────────
# 7. Performance — score update latency
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_update_performance(client: AsyncClient):
    """Score update should return new rank quickly (targeting <5ms for Redis ops)."""
    uid = await create_user(client, "perf_user")
    await create_leaderboard(client, "test_perf_lb")

    start = time.time()
    result = await submit_score(client, "test_perf_lb", uid, 42.0)
    elapsed_ms = (time.time() - start) * 1000

    assert result["new_rank"] == 1
    # Allow generous headroom for CI / test overhead; Redis ops themselves are <5ms
    assert elapsed_ms < 500, f"Score update took {elapsed_ms:.1f}ms — too slow"


# ──────────────────────────────────────────────────────────────
# 8. Rate limiting — max 10 updates per user per minute
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rate_limit_blocks_after_10(client: AsyncClient):
    """11th score update within 60s should be rejected with 429."""
    uid = await create_user(client, "ratelimit_user")
    await create_leaderboard(client, "test_rl_lb")

    # First 10 should succeed
    for i in range(10):
        resp = await client.post(f"/leaderboards/test_rl_lb/scores", json={
            "user_id": uid,
            "delta": 1.0,
        })
        assert resp.status_code == 201, f"Request {i+1} failed: {resp.text}"

    # 11th should be rate-limited
    resp = await client.post(f"/leaderboards/test_rl_lb/scores", json={
        "user_id": uid,
        "delta": 1.0,
    })
    assert resp.status_code == 429
    assert "Rate limit" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_rate_limit_per_user(client: AsyncClient):
    """Rate limit is per-user — different users have independent limits."""
    u1 = await create_user(client, "rl_user1")
    u2 = await create_user(client, "rl_user2")
    await create_leaderboard(client, "test_rl2_lb")

    # Exhaust u1's rate limit
    for _ in range(10):
        await client.post(f"/leaderboards/test_rl2_lb/scores", json={
            "user_id": u1, "delta": 1.0,
        })

    # u1 should be blocked
    resp1 = await client.post(f"/leaderboards/test_rl2_lb/scores", json={
        "user_id": u1, "delta": 1.0,
    })
    assert resp1.status_code == 429

    # u2 should still work
    resp2 = await client.post(f"/leaderboards/test_rl2_lb/scores", json={
        "user_id": u2, "delta": 1.0,
    })
    assert resp2.status_code == 201

