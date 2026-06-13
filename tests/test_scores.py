"""Tests for LiveBoard Phase 1 — scores, users, health."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.main import app
from backend.redis_client import get_redis, redis_client

# ── In-memory SQLite for tests (swap to test PG if preferred) ──
# NOTE: For full compatibility with UUID/PG-specific features, use a real
# test Postgres instance. SQLite is used here for zero-dependency CI.

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Health ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "redis" in data
    assert "db" in data


# ── Users CRUD ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    resp = await client.post("/users", json={
        "username": "alice",
        "display_name": "Alice W.",
        "region": "US-EAST",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "alice"
    assert data["display_name"] == "Alice W."
    assert "id" in data


@pytest.mark.asyncio
async def test_create_duplicate_user(client: AsyncClient):
    await client.post("/users", json={"username": "bob"})
    resp = await client.post("/users", json={"username": "bob"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_user(client: AsyncClient):
    create_resp = await client.post("/users", json={"username": "charlie"})
    user_id = create_resp.json()["id"]

    resp = await client.get(f"/users/{user_id}")
    assert resp.status_code == 200
    assert resp.json()["username"] == "charlie"


@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient):
    resp = await client.get("/users/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
