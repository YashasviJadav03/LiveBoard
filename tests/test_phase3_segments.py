"""Tests for LiveBoard Phase 3 — Segmented Leaderboards.

Covers:
- Single POST /scores writes to all 4 Redis segment keys
- GET /top?segment=daily|weekly|all_time|regional
- GET /friends/{user_id}/top — friends-only ranking
- GET /segments — lists segments with member counts
- Daily/weekly key TTLs
- Regional leaderboard only shows that region's users
- resolve_redis_key() helper
"""

import asyncio
import time

import pytest
from httpx import AsyncClient

from backend.routers.scores import resolve_redis_key


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


# ──────────────────────────────────────────────────────────────
# 1. resolve_redis_key() unit tests
# ──────────────────────────────────────────────────────────────

def test_resolve_redis_key_all_time():
    key = resolve_redis_key("game1", "all_time")
    assert key == "lb:game1:all"


def test_resolve_redis_key_daily():
    key = resolve_redis_key("game1", "daily")
    assert key.startswith("lb:game1:day:")


def test_resolve_redis_key_weekly():
    key = resolve_redis_key("game1", "weekly")
    assert key.startswith("lb:game1:week:")


def test_resolve_redis_key_regional():
    key = resolve_redis_key("game1", "regional", region="US-EAST")
    assert key == "lb:game1:region:US-EAST"


def test_resolve_redis_key_regional_requires_region():
    with pytest.raises(ValueError, match="region"):
        resolve_redis_key("game1", "regional")


def test_resolve_redis_key_unknown_segment():
    with pytest.raises(ValueError, match="Unknown segment"):
        resolve_redis_key("game1", "invalid_segment")


# ──────────────────────────────────────────────────────────────
# 2. Single POST /scores writes to all 4 Redis segment keys
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_update_writes_all_segments(client: AsyncClient, fake_redis):
    """A single POST /scores must write to all-time, daily, weekly, and regional keys."""
    uid = await create_user(client, "seg_user1", region="US-EAST")
    await create_leaderboard(client, "p3_seg_lb")

    await submit_score(client, "p3_seg_lb", uid, 100.0)

    # Verify all 4 keys exist in Redis
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    all_key = "lb:p3_seg_lb:all"
    day_key = f"lb:p3_seg_lb:day:{now.strftime('%Y-%m-%d')}"
    week_key = f"lb:p3_seg_lb:week:{now.strftime('%Y-W%W')}"
    region_key = "lb:p3_seg_lb:region:US-EAST"

    pipe = fake_redis.pipeline(transaction=True)
    pipe.zscore(all_key, uid)
    pipe.zscore(day_key, uid)
    pipe.zscore(week_key, uid)
    pipe.zscore(region_key, uid)
    scores = await pipe.execute()

    # All 4 should have non-None scores
    for i, key_name in enumerate([all_key, day_key, week_key, region_key]):
        assert scores[i] is not None, f"Missing score in {key_name}"


@pytest.mark.asyncio
async def test_score_update_no_region_writes_3_segments(client: AsyncClient, fake_redis):
    """User without a region should only write to 3 keys (no regional)."""
    uid = await create_user(client, "no_region_user")
    await create_leaderboard(client, "p3_noreg_lb")

    await submit_score(client, "p3_noreg_lb", uid, 50.0)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    all_score = await fake_redis.zscore("lb:p3_noreg_lb:all", uid)
    day_score = await fake_redis.zscore(
        f"lb:p3_noreg_lb:day:{now.strftime('%Y-%m-%d')}", uid
    )
    week_score = await fake_redis.zscore(
        f"lb:p3_noreg_lb:week:{now.strftime('%Y-W%W')}", uid
    )

    assert all_score is not None
    assert day_score is not None
    assert week_score is not None

    # No regional keys should exist for this leaderboard
    region_keys = await fake_redis.keys("lb:p3_noreg_lb:region:*")
    assert len(region_keys) == 0


# ──────────────────────────────────────────────────────────────
# 3. GET /top with segment parameter
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_top_segment_daily(client: AsyncClient):
    """GET /top?segment=daily returns today's scores."""
    uid = await create_user(client, "daily_user")
    await create_leaderboard(client, "p3_daily_lb")

    await submit_score(client, "p3_daily_lb", uid, 100.0)

    resp = await client.get("/leaderboards/p3_daily_lb/top?segment=daily")
    assert resp.status_code == 200
    data = resp.json()
    assert data["segment"] == "daily"
    assert data["total_users"] == 1
    assert data["entries"][0]["user_id"] == uid
    assert data["entries"][0]["score"] == 100


@pytest.mark.asyncio
async def test_top_segment_weekly(client: AsyncClient):
    """GET /top?segment=weekly returns this week's scores."""
    uid = await create_user(client, "weekly_user")
    await create_leaderboard(client, "p3_weekly_lb")

    await submit_score(client, "p3_weekly_lb", uid, 250.0)

    resp = await client.get("/leaderboards/p3_weekly_lb/top?segment=weekly")
    assert resp.status_code == 200
    data = resp.json()
    assert data["segment"] == "weekly"
    assert data["total_users"] == 1
    assert data["entries"][0]["score"] == 250


@pytest.mark.asyncio
async def test_top_segment_regional(client: AsyncClient):
    """GET /top?segment=regional&region=X only shows that region's users."""
    u_east = await create_user(client, "east_user", region="US-EAST")
    u_west = await create_user(client, "west_user", region="US-WEST")
    await create_leaderboard(client, "p3_region_lb")

    await submit_score(client, "p3_region_lb", u_east, 100.0)
    await submit_score(client, "p3_region_lb", u_west, 200.0)

    # Query US-EAST region — should only contain u_east
    resp = await client.get("/leaderboards/p3_region_lb/top?segment=regional&region=US-EAST")
    assert resp.status_code == 200
    data = resp.json()
    assert data["segment"] == "regional"
    assert data["total_users"] == 1
    assert data["entries"][0]["user_id"] == u_east
    assert data["entries"][0]["score"] == 100

    # Query US-WEST region — should only contain u_west
    resp2 = await client.get("/leaderboards/p3_region_lb/top?segment=regional&region=US-WEST")
    data2 = resp2.json()
    assert data2["total_users"] == 1
    assert data2["entries"][0]["user_id"] == u_west


@pytest.mark.asyncio
async def test_top_segment_regional_requires_region_param(client: AsyncClient):
    """segment=regional without region param should return 400."""
    await create_leaderboard(client, "p3_reg_err_lb")

    resp = await client.get("/leaderboards/p3_reg_err_lb/top?segment=regional")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_top_default_is_all_time(client: AsyncClient):
    """GET /top without segment param defaults to all_time."""
    uid = await create_user(client, "default_seg_user")
    await create_leaderboard(client, "p3_default_lb")

    await submit_score(client, "p3_default_lb", uid, 42.0)

    resp = await client.get("/leaderboards/p3_default_lb/top")
    assert resp.status_code == 200
    data = resp.json()
    assert data["segment"] == "all_time"
    assert data["total_users"] == 1


# ──────────────────────────────────────────────────────────────
# 4. Daily/weekly key TTLs
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_daily_key_has_ttl(client: AsyncClient, fake_redis):
    """Daily key should have a TTL set (≤ 172800s = 2 days)."""
    uid = await create_user(client, "ttl_daily_user")
    await create_leaderboard(client, "p3_ttl_lb")

    await submit_score(client, "p3_ttl_lb", uid, 10.0)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    day_key = f"lb:p3_ttl_lb:day:{now.strftime('%Y-%m-%d')}"

    ttl = await fake_redis.ttl(day_key)
    assert ttl > 0, "Daily key should have a positive TTL"
    assert ttl <= 172800, f"Daily TTL should be ≤ 172800s, got {ttl}"


@pytest.mark.asyncio
async def test_weekly_key_has_ttl(client: AsyncClient, fake_redis):
    """Weekly key should have a TTL set (≤ 691200s = 8 days)."""
    uid = await create_user(client, "ttl_weekly_user")
    await create_leaderboard(client, "p3_ttl_w_lb")

    await submit_score(client, "p3_ttl_w_lb", uid, 10.0)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    week_key = f"lb:p3_ttl_w_lb:week:{now.strftime('%Y-W%W')}"

    ttl = await fake_redis.ttl(week_key)
    assert ttl > 0, "Weekly key should have a positive TTL"
    assert ttl <= 691200, f"Weekly TTL should be ≤ 691200s, got {ttl}"


# ──────────────────────────────────────────────────────────────
# 5. GET /friends/{user_id}/top — friends leaderboard
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_friends_leaderboard_basic(client: AsyncClient):
    """Friends leaderboard shows correct ranking among friends only."""
    u1 = await create_user(client, "friend_alice")
    u2 = await create_user(client, "friend_bob")
    u3 = await create_user(client, "friend_charlie")
    u_stranger = await create_user(client, "stranger_dave")
    await create_leaderboard(client, "p3_friends_lb")

    # u1 is friends with u2 and u3, but NOT u_stranger
    await add_friendship(client, u1, u2)
    await add_friendship(client, u1, u3)

    # Everyone gets a score
    await submit_score(client, "p3_friends_lb", u1, 100.0)
    await submit_score(client, "p3_friends_lb", u2, 300.0)
    await submit_score(client, "p3_friends_lb", u3, 200.0)
    await submit_score(client, "p3_friends_lb", u_stranger, 999.0)  # not a friend

    # Get u1's friends leaderboard
    resp = await client.get(f"/leaderboards/p3_friends_lb/friends/{u1}/top?limit=10")
    assert resp.status_code == 200
    data = resp.json()

    assert data["leaderboard_id"] == "p3_friends_lb"
    assert data["user_id"] == u1
    # u1, u2, u3 are in the friend group; u_stranger is NOT
    assert data["total_friends"] == 3

    entries = data["entries"]
    assert len(entries) == 3

    # u2 (300) should be rank 1, u3 (200) rank 2, u1 (100) rank 3
    assert entries[0]["score"] == 300
    assert entries[0]["rank"] == 1
    assert entries[0]["user_id"] == u2

    assert entries[1]["score"] == 200
    assert entries[1]["rank"] == 2
    assert entries[1]["user_id"] == u3

    assert entries[2]["score"] == 100
    assert entries[2]["rank"] == 3
    assert entries[2]["user_id"] == u1

    # Stranger should NOT appear
    entry_ids = [e["user_id"] for e in entries]
    assert u_stranger not in entry_ids


@pytest.mark.asyncio
async def test_friends_leaderboard_includes_self(client: AsyncClient):
    """The requesting user should appear in their own friends leaderboard."""
    u1 = await create_user(client, "self_inc_user")
    await create_leaderboard(client, "p3_self_lb")

    # No friends — just self
    await submit_score(client, "p3_self_lb", u1, 42.0)

    resp = await client.get(f"/leaderboards/p3_self_lb/friends/{u1}/top")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_friends"] == 1
    assert data["entries"][0]["user_id"] == u1
    assert data["entries"][0]["score"] == 42


@pytest.mark.asyncio
async def test_friends_leaderboard_respects_limit(client: AsyncClient):
    """Friends leaderboard limit parameter should cap the results."""
    users = []
    await create_leaderboard(client, "p3_lim_lb")
    u_main = await create_user(client, "lim_main")

    for i in range(5):
        uid = await create_user(client, f"lim_friend_{i}")
        users.append(uid)
        await add_friendship(client, u_main, uid)
        await submit_score(client, "p3_lim_lb", uid, (i + 1) * 10.0)

    await submit_score(client, "p3_lim_lb", u_main, 5.0)

    resp = await client.get(f"/leaderboards/p3_lim_lb/friends/{u_main}/top?limit=3")
    data = resp.json()
    assert len(data["entries"]) == 3
    assert data["total_friends"] == 6  # 5 friends + self


@pytest.mark.asyncio
async def test_friends_leaderboard_resolves_usernames(client: AsyncClient):
    """Friends leaderboard should resolve usernames from PostgreSQL."""
    u1 = await create_user(client, "named_friend_a")
    u2 = await create_user(client, "named_friend_b")
    await create_leaderboard(client, "p3_fname_lb")

    await add_friendship(client, u1, u2)
    await submit_score(client, "p3_fname_lb", u1, 10.0)
    await submit_score(client, "p3_fname_lb", u2, 20.0)

    resp = await client.get(f"/leaderboards/p3_fname_lb/friends/{u1}/top")
    data = resp.json()
    assert data["entries"][0]["username"] == "named_friend_b"
    assert data["entries"][1]["username"] == "named_friend_a"


# ──────────────────────────────────────────────────────────────
# 6. GET /segments — list available segments
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_segments_listing(client: AsyncClient):
    """GET /segments should return all segment types with member counts."""
    u1 = await create_user(client, "seg_list_u1", region="EU-WEST")
    u2 = await create_user(client, "seg_list_u2", region="US-EAST")
    await create_leaderboard(client, "p3_seglist_lb")

    await submit_score(client, "p3_seglist_lb", u1, 100.0)
    await submit_score(client, "p3_seglist_lb", u2, 200.0)

    resp = await client.get("/leaderboards/p3_seglist_lb/segments")
    assert resp.status_code == 200
    data = resp.json()

    assert data["leaderboard_id"] == "p3_seglist_lb"
    segments = data["segments"]

    # Should have at least: all_time, daily, weekly, + 2 regional
    seg_names = [s["segment"] for s in segments]
    assert "all_time" in seg_names
    assert "daily" in seg_names
    assert "weekly" in seg_names

    # Regional segments for EU-WEST and US-EAST
    regional_segs = [s for s in segments if s["segment"].startswith("regional:")]
    assert len(regional_segs) == 2

    # All-time should have 2 members
    all_time_seg = next(s for s in segments if s["segment"] == "all_time")
    assert all_time_seg["member_count"] == 2


@pytest.mark.asyncio
async def test_segments_shows_zero_count_for_empty(client: AsyncClient):
    """Segments with no data should show member_count=0."""
    await create_leaderboard(client, "p3_empty_seg_lb")

    resp = await client.get("/leaderboards/p3_empty_seg_lb/segments")
    data = resp.json()

    all_seg = next(s for s in data["segments"] if s["segment"] == "all_time")
    assert all_seg["member_count"] == 0


# ──────────────────────────────────────────────────────────────
# 7. Performance — segment queries < 10ms target
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_segment_query_performance(client: AsyncClient):
    """All segment queries should complete quickly."""
    uid = await create_user(client, "perf_seg_user", region="US")
    await create_leaderboard(client, "p3_perf_lb")
    await submit_score(client, "p3_perf_lb", uid, 42.0)

    start = time.time()
    resp = await client.get("/leaderboards/p3_perf_lb/top?segment=daily")
    elapsed_ms = (time.time() - start) * 1000

    assert resp.status_code == 200
    # Generous headroom for CI/test overhead
    assert elapsed_ms < 500, f"Segment query took {elapsed_ms:.1f}ms — too slow"
