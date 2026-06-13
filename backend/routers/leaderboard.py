"""Leaderboard rank query endpoints."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.user import ScoreEvent, User
from backend.schemas.score import LeaderboardEntry, LeaderboardResponse

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/{leaderboard_id}", response_model=LeaderboardResponse)
async def get_leaderboard(
    leaderboard_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Return ranked leaderboard for a given leaderboard_id.

    Uses the latest total_score per user from score_events.
    """
    # Subquery: latest score event per user for this leaderboard
    latest_sq = (
        select(
            ScoreEvent.user_id,
            func.max(ScoreEvent.recorded_at).label("max_time"),
        )
        .where(ScoreEvent.leaderboard_id == leaderboard_id)
        .group_by(ScoreEvent.user_id)
        .subquery()
    )

    # Join back to get the total_score at that timestamp
    ranked_q = (
        select(
            ScoreEvent.user_id,
            User.username,
            ScoreEvent.total_score,
        )
        .join(latest_sq, (ScoreEvent.user_id == latest_sq.c.user_id) & (ScoreEvent.recorded_at == latest_sq.c.max_time))
        .join(User, User.id == ScoreEvent.user_id)
        .where(ScoreEvent.leaderboard_id == leaderboard_id)
        .order_by(ScoreEvent.total_score.desc())
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(ranked_q)
    rows = result.all()

    entries = [
        LeaderboardEntry(
            user_id=row.user_id,
            username=row.username,
            total_score=row.total_score,
            rank=offset + idx + 1,
        )
        for idx, row in enumerate(rows)
    ]

    # total distinct users on this leaderboard
    count_q = (
        select(func.count(func.distinct(ScoreEvent.user_id)))
        .where(ScoreEvent.leaderboard_id == leaderboard_id)
    )
    total = (await db.execute(count_q)).scalar_one()

    return LeaderboardResponse(
        leaderboard_id=leaderboard_id,
        entries=entries,
        total=total,
    )
