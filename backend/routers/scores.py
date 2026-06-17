"""Score update endpoints — Phase 2: Redis-backed ranking engine."""

import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import ScoreEvent, User
from backend.redis_client import get_redis
from backend.schemas.score import LegacyScoreSubmit, ScoreUpdateResponse

router = APIRouter(prefix="/scores", tags=["scores"])


# ── Composite-score helpers ──────────────────────────────────

TIEBREAK_SCALE = 1e10


def composite_score(actual_score: float, achieved_at_ts: float) -> float:
    """Encode actual score + timestamp for tie-breaking.

    Higher actual score → higher composite.
    Among equal scores, *earlier* timestamp → higher composite
    (because we subtract the timestamp).
    """
    return actual_score * TIEBREAK_SCALE + (TIEBREAK_SCALE - achieved_at_ts)


def extract_actual_score(composite: float) -> float:
    """Strip the tiebreak component, returning the user-visible score."""
    return int(composite / TIEBREAK_SCALE)


# ── POST /scores/{user_id}  (legacy endpoint kept) ──────────

@router.post(
    "/{user_id}",
    response_model=ScoreUpdateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_score_legacy(
    user_id: UUID,
    payload: LegacyScoreSubmit,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Legacy wrapper — delegates to the shared implementation."""
    return await _submit_score(
        lb_id=payload.leaderboard_id,
        user_id=user_id,
        delta=payload.score_delta,
        db=db,
        redis=redis,
    )


async def _submit_score(
    lb_id: str,
    user_id: UUID,
    delta: float,
    db: AsyncSession,
    redis,
) -> ScoreUpdateResponse:
    """Core score-update logic shared by both the legacy and Phase 2 routes.

    1. Verify the user exists in PostgreSQL.
    2. Read previous rank from Redis (pipelined).
    3. Compute composite score with tie-breaking timestamp.
    4. Update Redis sorted set atomically via pipeline.
    5. Read new rank from Redis.
    6. Insert a score_events row into PostgreSQL.
    7. Return the full rank-change response.
    """
    redis_key = f"lb:{lb_id}:all"
    user_key = str(user_id)
    now_ts = time.time()

    # ── 1. Verify user ────────────────────────────────────────
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ── 2. Read previous state (pipelined) ────────────────────
    pipe = redis.pipeline(transaction=True)
    pipe.zscore(redis_key, user_key)
    pipe.zrevrank(redis_key, user_key)
    prev_composite, prev_rank_raw = await pipe.execute()

    prev_actual = extract_actual_score(prev_composite) if prev_composite is not None else 0.0
    previous_rank = (prev_rank_raw + 1) if prev_rank_raw is not None else None  # 1-indexed

    # ── 3. Compute new composite ──────────────────────────────
    new_actual = prev_actual + delta
    new_composite = composite_score(new_actual, now_ts)

    # ── 4. Write new composite to Redis (pipelined) ──────────
    pipe2 = redis.pipeline(transaction=True)
    pipe2.zadd(redis_key, {user_key: new_composite})
    pipe2.zrevrank(redis_key, user_key)
    results = await pipe2.execute()
    new_rank_0 = results[1]  # 0-indexed
    new_rank = new_rank_0 + 1  # 1-indexed

    # ── 5. Persist to PostgreSQL ──────────────────────────────
    event = ScoreEvent(
        user_id=user_id,
        leaderboard_id=lb_id,
        score_delta=delta,
        total_score=new_actual,
    )
    db.add(event)
    await db.flush()

    # ── 6. Build response ─────────────────────────────────────
    rank_change = (previous_rank - new_rank) if previous_rank is not None else None

    return ScoreUpdateResponse(
        user_id=user_id,
        new_score=new_actual,
        new_rank=new_rank,
        previous_rank=previous_rank,
        rank_change=rank_change,
    )
