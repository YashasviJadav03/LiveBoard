"""Shared test fixtures for LiveBoard — single source of truth.

Solves two problems:
1. Multiple test files fighting over `app.dependency_overrides` (last-imported wins).
2. Module-level `FakeRedis()` bound to a stale event loop on Python 3.10.

Fix: create *one* SQLite engine and *per-test* FakeRedis, wired up through
`conftest.py` so every test file sees the same overrides.
"""

import pytest
import pytest_asyncio
import fakeredis.aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import Base, get_db
from backend.main import app
from backend.redis_client import get_redis

# ── Single test database engine ──────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_liveboard.db"

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


# ── Per-test FakeRedis (avoids event-loop mismatch) ──────────

@pytest_asyncio.fixture(autouse=True)
async def setup_database_and_redis():
    """Create tables + fresh FakeRedis before each test; tear down after."""
    import backend.routers.scores as scores_module
    import backend.routers.leaderboard as lb_module
    import backend.routers.websocket as ws_module
    from backend.connection_manager import manager

    # ── Fresh FakeRedis each test (same event loop) ──────────
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def override_get_redis():
        return fake_redis

    app.dependency_overrides[get_redis] = override_get_redis

    # Patch module-level redis_client references used by routers
    # that bypass dependency injection.
    ws_module.redis_client = fake_redis

    # ── Create all tables ────────────────────────────────────
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield fake_redis

    # ── Teardown ─────────────────────────────────────────────
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await fake_redis.flushall()
    await fake_redis.aclose()

    # Clear WebSocket connection manager state
    manager.connections.clear()


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def fake_redis(setup_database_and_redis):
    """Expose the per-test FakeRedis instance to tests that need direct access."""
    return setup_database_and_redis
