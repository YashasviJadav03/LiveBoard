"""Load test setup — creates 1000 test users and the load test leaderboard.

Run this BEFORE starting locust:
    python loadtests/setup_load_test.py
"""

import asyncio
import time
import uuid

import asyncpg
import redis.asyncio as aioredis

PG_DSN = "postgresql://liveboard:liveboard123@localhost:5432/liveboard"
REDIS_URL = "redis://localhost:6379/0"
LB_ID = "load_test_lb"
NUM_USERS = 1000


async def main():
    print("=" * 60)
    print("  Load Test Setup")
    print("=" * 60)
    t_start = time.time()

    pool = await asyncpg.create_pool(PG_DSN, min_size=2, max_size=5)
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    # Verify connections
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT 1") == 1
    assert await redis.ping()
    print("[OK] Connected to PostgreSQL and Redis")

    # Create leaderboard (idempotent)
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO leaderboards (id, name, description, is_active)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (id) DO NOTHING""",
            LB_ID, "Load Test Leaderboard", "For benchmarking", True,
        )
    print(f"[OK] Leaderboard '{LB_ID}' ready")

    # Generate 1000 user UUIDs
    user_ids = [uuid.uuid4() for _ in range(NUM_USERS)]

    # Check how many already exist
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE username LIKE 'loadtest_user_%'"
        )

    if existing >= NUM_USERS:
        print(f"[OK] {existing} load test users already exist, skipping creation")
        # Fetch their IDs
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id FROM users WHERE username LIKE 'loadtest_user_%' LIMIT $1",
                NUM_USERS,
            )
            user_ids = [row["id"] for row in rows]
    else:
        # Delete any partial set and recreate
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM users WHERE username LIKE 'loadtest_user_%'")

            regions = ["Gujarat", "Mumbai", "Delhi", "Bangalore", "Chennai"]
            batch = [
                (
                    user_ids[i],
                    f"loadtest_user_{i:04d}",
                    f"Load Test User {i}",
                    regions[i % len(regions)],
                )
                for i in range(NUM_USERS)
            ]
            await conn.executemany(
                """INSERT INTO users (id, username, display_name, region)
                   VALUES ($1, $2, $3, $4)""",
                batch,
            )
        print(f"[OK] Created {NUM_USERS} load test users")

    # Write user IDs to a file so locust can read them
    ids_file = "loadtests/user_ids.txt"
    with open(ids_file, "w") as f:
        for uid in user_ids:
            f.write(f"{uid}\n")
    print(f"[OK] Wrote {len(user_ids)} user IDs to {ids_file}")

    # Seed initial scores so rank queries work (give each user a base score)
    print("  Seeding initial scores in Redis...")
    pipe = redis.pipeline(transaction=False)
    now_ts = time.time()
    for uid in user_ids:
        base_score = 100.0  # small initial score
        comp = base_score * 1e10 + (1e10 - now_ts)
        pipe.zadd(f"lb:{LB_ID}:all", {str(uid): comp})
    await pipe.execute()
    print(f"[OK] Seeded {len(user_ids)} users in Redis sorted set")

    elapsed = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"  Setup complete in {elapsed:.1f}s")
    print(f"  Now run: locust -f loadtests/locustfile.py --host=http://localhost:8000")
    print(f"  Open: http://localhost:8089")
    print(f"{'=' * 60}")

    await pool.close()
    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
