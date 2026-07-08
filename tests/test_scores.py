"""Tests for LiveBoard Phase 1 — Acceptance Criteria.

Covers:
✓ GET /health returns {"status": "ok", "redis": "connected", "db": "connected"}
✓ POST /users creates a user and returns their UUID
✓ Redis ping returns PONG from Python client
✓ All DB tables exist (users, friendships, score_events, leaderboards)
✓ Duplicate username returns 409
✓ GET /users/{id} returns the user
✓ GET /users/{bad_id} returns 404
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import inspect

from tests.conftest import test_engine


# ══════════════════════════════════════════════════════════════
# Acceptance Criterion 1:
# GET /health returns {"status": "ok", "redis": "connected", "db": "connected"}
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_health_returns_ok_with_both_services(client: AsyncClient):
    """GET /health returns status=ok when DB and Redis are both reachable."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["redis"] == "connected"
    assert data["db"] == "connected"


@pytest.mark.asyncio
async def test_health_response_schema(client: AsyncClient):
    """Health response contains exactly the three required keys."""
    resp = await client.get("/health")
    data = resp.json()
    assert set(data.keys()) == {"status", "redis", "db"}


# ══════════════════════════════════════════════════════════════
# Acceptance Criterion 2:
# POST /users creates a user and returns their UUID
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_create_user_returns_uuid(client: AsyncClient):
    """POST /users returns 201 with a valid UUID in the response."""
    resp = await client.post("/users", json={
        "username": "alice",
        "display_name": "Alice W.",
        "region": "US-EAST",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "alice"
    assert data["display_name"] == "Alice W."
    assert data["region"] == "US-EAST"
    # Verify the id is a valid UUID
    assert "id" in data
    parsed = uuid.UUID(data["id"])  # will raise if not valid
    assert str(parsed) == data["id"]


@pytest.mark.asyncio
async def test_create_user_minimal_fields(client: AsyncClient):
    """POST /users with only username (minimal payload) works."""
    resp = await client.post("/users", json={"username": "bob"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "bob"
    assert "id" in data
    uuid.UUID(data["id"])  # valid UUID


@pytest.mark.asyncio
async def test_create_user_has_created_at(client: AsyncClient):
    """POST /users response includes a created_at timestamp."""
    resp = await client.post("/users", json={"username": "chrono"})
    assert resp.status_code == 201
    data = resp.json()
    assert "created_at" in data
    assert data["created_at"] is not None


@pytest.mark.asyncio
async def test_create_duplicate_user_returns_409(client: AsyncClient):
    """POST /users with a duplicate username returns 409 Conflict."""
    await client.post("/users", json={"username": "dupe_user"})
    resp = await client.post("/users", json={"username": "dupe_user"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_user_by_id(client: AsyncClient):
    """GET /users/{id} returns the user created by POST."""
    create_resp = await client.post("/users", json={"username": "charlie"})
    user_id = create_resp.json()["id"]

    resp = await client.get(f"/users/{user_id}")
    assert resp.status_code == 200
    assert resp.json()["username"] == "charlie"
    assert resp.json()["id"] == user_id


@pytest.mark.asyncio
async def test_get_user_not_found_returns_404(client: AsyncClient):
    """GET /users/{nonexistent_id} returns 404."""
    resp = await client.get("/users/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════
# Acceptance Criterion 3:
# Redis ping returns PONG from Python client
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_redis_ping_returns_pong(fake_redis):
    """Direct ping on the Redis client returns True (PONG)."""
    pong = await fake_redis.ping()
    assert pong is True


# ══════════════════════════════════════════════════════════════
# Acceptance Criterion 4:
# All DB tables exist — users, friendships, score_events, leaderboards
# ══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_db_tables_exist():
    """After startup, all 4 required tables are created in the database."""
    expected_tables = {"users", "friendships", "score_events", "leaderboards"}

    async with test_engine.connect() as conn:
        table_names = await conn.run_sync(
            lambda sync_conn: set(inspect(sync_conn).get_table_names())
        )

    assert expected_tables.issubset(table_names), (
        f"Missing tables: {expected_tables - table_names}"
    )


@pytest.mark.asyncio
async def test_users_table_has_required_columns():
    """The users table has all required columns."""
    async with test_engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: {
                c["name"] for c in inspect(sync_conn).get_columns("users")
            }
        )
    required = {"id", "username", "display_name", "region", "avatar_url", "created_at"}
    assert required.issubset(columns), f"Missing columns: {required - columns}"


@pytest.mark.asyncio
async def test_score_events_table_has_required_columns():
    """The score_events table has all required columns."""
    async with test_engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: {
                c["name"] for c in inspect(sync_conn).get_columns("score_events")
            }
        )
    required = {"id", "user_id", "leaderboard_id", "score_delta", "total_score_after", "rank_after", "source", "recorded_at"}
    assert required.issubset(columns), f"Missing columns: {required - columns}"


@pytest.mark.asyncio
async def test_leaderboards_table_has_required_columns():
    """The leaderboards table has all required columns."""
    async with test_engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: {
                c["name"] for c in inspect(sync_conn).get_columns("leaderboards")
            }
        )
    required = {"id", "name", "description", "is_active", "created_at"}
    assert required.issubset(columns), f"Missing columns: {required - columns}"


@pytest.mark.asyncio
async def test_friendships_table_has_required_columns():
    """The friendships table has all required columns."""
    async with test_engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: {
                c["name"] for c in inspect(sync_conn).get_columns("friendships")
            }
        )
    required = {"user_id", "friend_id"}
    assert required.issubset(columns), f"Missing columns: {required - columns}"


@pytest.mark.asyncio
async def test_rank_snapshots_table_has_required_columns():
    """The rank_snapshots table has all required columns."""
    async with test_engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: {
                c["name"] for c in inspect(sync_conn).get_columns("rank_snapshots")
            }
        )
    required = {"id", "leaderboard_id", "user_id", "rank", "score", "snapshotted_at"}
    assert required.issubset(columns), f"Missing columns: {required - columns}"
# ══════════════════════════════════════════════════════════════
# Bonus: docker-compose.yml structure validation
# ══════════════════════════════════════════════════════════════

def test_docker_compose_has_required_services():
    """docker-compose.yml defines postgres, redis, and backend services."""
    import yaml

    with open("docker-compose.yml", "r") as f:
        config = yaml.safe_load(f)

    services = set(config.get("services", {}).keys())
    required = {"postgres", "redis", "backend"}
    assert required.issubset(services), f"Missing services: {required - services}"


def test_docker_compose_backend_depends_on_healthy_services():
    """Backend service depends on postgres and redis with health checks."""
    import yaml

    with open("docker-compose.yml", "r") as f:
        config = yaml.safe_load(f)

    backend = config["services"]["backend"]
    depends = backend.get("depends_on", {})

    assert "postgres" in depends
    assert "redis" in depends
    assert depends["postgres"].get("condition") == "service_healthy"
    assert depends["redis"].get("condition") == "service_healthy"


def test_docker_compose_correct_ports():
    """Services expose the correct ports."""
    import yaml

    with open("docker-compose.yml", "r") as f:
        config = yaml.safe_load(f)

    services = config["services"]
    assert "5432:5432" in services["postgres"]["ports"]
    assert "6379:6379" in services["redis"]["ports"]
    assert "8000:8000" in services["backend"]["ports"]


def test_docker_compose_healthchecks_defined():
    """Postgres and Redis services have health checks configured."""
    import yaml

    with open("docker-compose.yml", "r") as f:
        config = yaml.safe_load(f)

    assert "healthcheck" in config["services"]["postgres"]
    assert "healthcheck" in config["services"]["redis"]
