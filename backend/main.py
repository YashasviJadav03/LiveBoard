"""LiveBoard — FastAPI application entry point."""

from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import Base, engine, get_db
from backend.models import Friendship, Leaderboard, User  # noqa: F401 — ensure models are registered
from backend.redis_client import redis_client
from backend.routers import leaderboard, scores, websocket
from backend.schemas.score import (
    FriendshipResponse,
    HealthResponse,
    UserCreate,
    UserResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables. Shutdown: dispose engine + close Redis."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    await redis_client.aclose()


app = FastAPI(
    title="LiveBoard",
    description="Real-time leaderboard service",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Register routers ─────────────────────────────────────────
app.include_router(scores.router)
app.include_router(leaderboard.router)
app.include_router(websocket.router)


# ── Core endpoints ────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Check connectivity to PostgreSQL and Redis."""
    db_status = "disconnected"
    redis_status = "disconnected"

    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        pass

    try:
        pong = await redis_client.ping()
        if pong:
            redis_status = "connected"
    except Exception:
        pass

    overall = "ok" if db_status == "connected" and redis_status == "connected" else "degraded"
    return HealthResponse(status=overall, redis=redis_status, db=db_status)


@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    """Create a new user."""
    # check for duplicate username
    existing = await db.execute(select(User).where(User.username == payload.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        username=payload.username,
        display_name=payload.display_name,
        region=payload.region,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a user by their ID."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.post(
    "/users/{user_id}/friends/{friend_id}",
    response_model=FriendshipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_friendship(
    user_id: UUID,
    friend_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Add a bidirectional friendship between two users."""
    if user_id == friend_id:
        raise HTTPException(status_code=400, detail="Cannot befriend yourself")

    # verify both users exist
    user = await db.get(User, user_id)
    friend = await db.get(User, friend_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    if not friend:
        raise HTTPException(status_code=404, detail=f"User {friend_id} not found")

    # check if friendship already exists
    existing = await db.execute(
        select(Friendship).where(
            Friendship.user_id == user_id,
            Friendship.friend_id == friend_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Friendship already exists")

    # create bidirectional friendship
    db.add(Friendship(user_id=user_id, friend_id=friend_id))
    db.add(Friendship(user_id=friend_id, friend_id=user_id))
    await db.flush()

    return FriendshipResponse(
        user_id=user_id,
        friend_id=friend_id,
        message="Friendship created",
    )
