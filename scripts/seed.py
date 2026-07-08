"""Seed script â€” generates realistic demo data for LiveBoard.

Creates:
  - 100 users with Indian names across 5 regions
  - 3 leaderboards
  - Friendship graph (5â€“15 friends per user)
  - 30 days of score history (~22k events)
  - Redis warm-up (replays scores into all Redis keys)

Usage:
  # Make sure Docker is running first:
  docker compose up -d

  # Then run the seed script:
  python scripts/seed.py
"""

import asyncio
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import redis.asyncio as aioredis
from faker import Faker

# â”€â”€ Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
PG_DSN = "postgresql://liveboard:liveboard123@localhost:5432/liveboard"
REDIS_URL = "redis://localhost:6379/0"

REGIONS = ["Gujarat", "Mumbai", "Delhi", "Bangalore", "Chennai"]
LB_IDS = ["coding_contest", "quiz_champ", "daily_challenge"]
LB_NAMES = {
    "coding_contest": "Coding Contest October",
    "quiz_champ": "Quiz Championship",
    "daily_challenge": "Daily Challenge",
}

NUM_USERS = 100
DAYS_OF_HISTORY = 30
MIN_FRIENDS = 5
MAX_FRIENDS = 15
MIN_EVENTS_PER_DAY = 0
MAX_EVENTS_PER_DAY = 5
MIN_DELTA = 10.0
MAX_DELTA = 200.0

TIEBREAK_SCALE = 1e10

fake = Faker("en_IN")
random.seed(42)  # reproducible data


def composite_score(actual_score: float, ts: float) -> float:
    """Same composite encoding as the backend â€” for consistent tie-breaking."""
    return actual_score * TIEBREAK_SCALE + (TIEBREAK_SCALE - ts)


async def main():
    print("=" * 60)
    print("  LiveBoard Seed Script")
    print("=" * 60)
    t_start = time.time()

    # â”€â”€ Connect to PostgreSQL + Redis â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\n[1/6] Connecting to PostgreSQL and Redis...")
    pool = await asyncpg.create_pool(PG_DSN, min_size=2, max_size=5)
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    # Verify connectivity
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
        assert result == 1, "PostgreSQL connection failed"
    pong = await redis.ping()
    assert pong, "Redis connection failed"
    print("  âœ“ PostgreSQL connected")
    print("  âœ“ Redis connected")

    # â”€â”€ Clean existing data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\n[2/6] Cleaning existing data...")
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM score_events")
        await conn.execute("DELETE FROM rank_snapshots")
        await conn.execute("DELETE FROM friendships")
        await conn.execute("DELETE FROM leaderboards")
        await conn.execute("DELETE FROM users")
    await redis.flushdb()
    print("  âœ“ PostgreSQL tables cleared")
    print("  âœ“ Redis flushed")

    # â”€â”€ Create 100 users â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n[3/6] Creating {NUM_USERS} users...")
    users = []
    used_usernames = set()

    for _ in range(NUM_USERS):
        # Ensure unique usernames
        while True:
            username = fake.user_name()
            if username not in used_usernames:
                used_usernames.add(username)
                break

        user = {
            "id": uuid.uuid4(),
            "username": username,
            "display_name": fake.name(),
            "region": random.choice(REGIONS),
        }
        users.append(user)

    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO users (id, username, display_name, region, created_at)
               VALUES ($1, $2, $3, $4, $5)""",
            [
                (u["id"], u["username"], u["display_name"], u["region"],
                 datetime.now(timezone.utc) - timedelta(days=35))
                for u in users
            ],
        )

    region_counts = {}
    for u in users:
        region_counts[u["region"]] = region_counts.get(u["region"], 0) + 1
    print(f"  âœ“ {NUM_USERS} users created")
    for region, count in sorted(region_counts.items()):
        print(f"    {region}: {count} users")

    # â”€â”€ Create 3 leaderboards â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n[4/6] Creating {len(LB_IDS)} leaderboards...")
    async with pool.acquire() as conn:
        for lb_id in LB_IDS:
            await conn.execute(
                """INSERT INTO leaderboards (id, name, description, is_active, created_at)
                   VALUES ($1, $2, $3, $4, $5)""",
                lb_id, LB_NAMES[lb_id], f"Demo leaderboard: {LB_NAMES[lb_id]}",
                True, datetime.now(timezone.utc) - timedelta(days=35),
            )
    print(f"  âœ“ Leaderboards: {', '.join(LB_IDS)}")

    # â”€â”€ Create friendship graph â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n[5/6] Creating friendship connections...")
    friendships = set()
    for user in users:
        # Pick 5â€“15 friends (excluding self)
        possible_friends = [u for u in users if u["id"] != user["id"]]
        num_friends = random.randint(MIN_FRIENDS, MAX_FRIENDS)
        selected = random.sample(possible_friends, min(num_friends, len(possible_friends)))

        for friend in selected:
            # Add both directions (bidirectional)
            pair_a = (user["id"], friend["id"])
            pair_b = (friend["id"], user["id"])
            friendships.add(pair_a)
            friendships.add(pair_b)

    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO friendships (user_id, friend_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            list(friendships),
        )
    print(f"  âœ“ {len(friendships)} friendship links created")
    avg_friends = len(friendships) / NUM_USERS
    print(f"    Average friends per user: {avg_friends:.1f}")

    # â”€â”€ Generate 30 days of score history â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print(f"\n[6/6] Generating {DAYS_OF_HISTORY} days of score history...")
    now = datetime.now(timezone.utc)
    score_events = []

    # Track cumulative scores per user per leaderboard
    # { (user_id, lb_id) -> running_total }
    running_totals = {}

    for user in users:
        for lb_id in LB_IDS:
            total = 0.0
            rank_counter = 0

            for day_offset in range(DAYS_OF_HISTORY, 0, -1):
                events_today = random.randint(MIN_EVENTS_PER_DAY, MAX_EVENTS_PER_DAY)

                for event_idx in range(events_today):
                    delta = round(random.uniform(MIN_DELTA, MAX_DELTA), 2)
                    total += delta
                    rank_counter += 1

                    # Spread events across the day
                    hour = random.randint(8, 23)
                    minute = random.randint(0, 59)
                    ts = now - timedelta(days=day_offset, hours=-hour, minutes=-minute)

                    score_events.append({
                        "id": uuid.uuid4(),
                        "user_id": user["id"],
                        "leaderboard_id": lb_id,
                        "score_delta": delta,
                        "total_score_after": round(total, 2),
                        "rank_after": None,  # will be filled by Redis replay
                        "source": random.choice(["api", "api", "api", "bonus", "admin"]),
                        "recorded_at": ts,
                    })

            running_totals[(user["id"], lb_id)] = round(total, 2)

    # Sort by time (oldest first) for correct replay
    score_events.sort(key=lambda e: e["recorded_at"])

    # Batch insert into PostgreSQL
    print(f"  Inserting {len(score_events)} score events into PostgreSQL...")
    batch_size = 1000
    async with pool.acquire() as conn:
        for i in range(0, len(score_events), batch_size):
            batch = score_events[i : i + batch_size]
            await conn.executemany(
                """INSERT INTO score_events
                   (id, user_id, leaderboard_id, score_delta, total_score_after,
                    rank_after, source, recorded_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                [
                    (e["id"], e["user_id"], e["leaderboard_id"], e["score_delta"],
                     e["total_score_after"], e["rank_after"], e["source"], e["recorded_at"])
                    for e in batch
                ],
            )
            pct = min(100, int((i + batch_size) / len(score_events) * 100))
            print(f"    {pct}% inserted ({i + len(batch)}/{len(score_events)})")

    print(f"  âœ“ {len(score_events)} score events inserted")

    # â”€â”€ Redis warm-up: replay final scores â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\n  Warming up Redis with final scores...")
    now_ts = time.time()

    pipe = redis.pipeline(transaction=False)
    count = 0

    for (user_id, lb_id), total_score in running_totals.items():
        user = next(u for u in users if u["id"] == user_id)
        user_key = str(user_id)
        comp = composite_score(total_score, now_ts - random.uniform(0, 100))

        # All-time
        pipe.zadd(f"lb:{lb_id}:all", {user_key: comp})

        # Today (daily)
        day_key = f"lb:{lb_id}:day:{now.strftime('%Y-%m-%d')}"
        # Use a portion of today's score for the daily board
        today_score = round(total_score * random.uniform(0.05, 0.15), 2)
        day_comp = composite_score(today_score, now_ts - random.uniform(0, 50))
        pipe.zadd(day_key, {user_key: day_comp})
        pipe.expire(day_key, 172800)

        # This week (weekly)
        week_key = f"lb:{lb_id}:week:{now.strftime('%Y-W%W')}"
        week_score = round(total_score * random.uniform(0.2, 0.4), 2)
        week_comp = composite_score(week_score, now_ts - random.uniform(0, 50))
        pipe.zadd(week_key, {user_key: week_comp})
        pipe.expire(week_key, 691200)

        # Regional
        if user["region"]:
            region_key = f"lb:{lb_id}:region:{user['region']}"
            pipe.zadd(region_key, {user_key: comp})

        count += 1
        if count % 50 == 0:
            await pipe.execute()
            pipe = redis.pipeline(transaction=False)

    await pipe.execute()
    print(f"  âœ“ Redis warmed up with {count} user scores across {len(LB_IDS)} leaderboards")

    # â”€â”€ Verification â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("\n" + "=" * 60)
    print("  VERIFICATION")
    print("=" * 60)

    async with pool.acquire() as conn:
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        event_count = await conn.fetchval("SELECT COUNT(*) FROM score_events")
        avg_delta = await conn.fetchval("SELECT AVG(score_delta) FROM score_events")
        friendship_count = await conn.fetchval("SELECT COUNT(*) FROM friendships")
        lb_count = await conn.fetchval("SELECT COUNT(*) FROM leaderboards")

    print(f"\n  PostgreSQL:")
    print(f"    Users:        {user_count}")
    print(f"    Leaderboards: {lb_count}")
    print(f"    Friendships:  {friendship_count}")
    print(f"    Score events: {event_count}")
    print(f"    Avg delta:    {avg_delta:.2f}")

    print(f"\n  Redis:")
    for lb_id in LB_IDS:
        all_count = await redis.zcard(f"lb:{lb_id}:all")
        day_key = f"lb:{lb_id}:day:{now.strftime('%Y-%m-%d')}"
        day_count = await redis.zcard(day_key)
        week_key = f"lb:{lb_id}:week:{now.strftime('%Y-W%W')}"
        week_count = await redis.zcard(week_key)

        print(f"    {lb_id}:")
        print(f"      all_time: {all_count} users")
        print(f"      daily:    {day_count} users")
        print(f"      weekly:   {week_count} users")

        # Show top 5
        top5 = await redis.zrevrange(f"lb:{lb_id}:all", 0, 4, withscores=True)
        print(f"      Top 5:")
        for i, (uid, comp) in enumerate(top5):
            actual = int(comp / TIEBREAK_SCALE)
            async with pool.acquire() as conn:
                username = await conn.fetchval(
                    "SELECT username FROM users WHERE id = $1", uuid.UUID(uid)
                )
            print(f"        #{i+1} {username:20s} â†’ {actual:,} pts")

    # Regional breakdown
    print(f"\n  Regional keys:")
    for lb_id in LB_IDS[:1]:  # just show first LB
        for region in REGIONS:
            rkey = f"lb:{lb_id}:region:{region}"
            rcount = await redis.zcard(rkey)
            print(f"    {region:15s} â†’ {rcount} users")

    elapsed = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"  âœ… Seed complete in {elapsed:.1f}s")
    print(f"{'=' * 60}")

    # Cleanup
    await pool.close()
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
