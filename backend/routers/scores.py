"""Score update endpoints."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import ScoreEvent, User
from backend.schemas.score import ScoreEventResponse, ScoreSubmit

router = APIRouter(prefix="/scores", tags=["scores"])


@router.post("/{user_id}", response_model=ScoreEventResponse, status_code=status.HTTP_201_CREATED)
async def submit_score(
    user_id: UUID,
    payload: ScoreSubmit,
    db: AsyncSession = Depends(get_db),
):
    """Submit a new score event for a user on a given leaderboard."""
    # verify user exists
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # calculate running total for this user + leaderboard
    result = await db.execute(
        select(ScoreEvent.total_score)
        .where(
            ScoreEvent.user_id == user_id,
            ScoreEvent.leaderboard_id == payload.leaderboard_id,
        )
        .order_by(ScoreEvent.recorded_at.desc())
        .limit(1)
    )
    last_total = result.scalar_one_or_none() or Decimal("0.00")
    new_total = last_total + payload.score_delta

    event = ScoreEvent(
        user_id=user_id,
        leaderboard_id=payload.leaderboard_id,
        score_delta=payload.score_delta,
        total_score=new_total,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)
    return event
