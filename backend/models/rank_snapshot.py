"""SQLAlchemy model — RankSnapshot.

Hourly snapshot of top 100 per leaderboard.
Enables "rank history over time" charts.
Written by a background job, never by the API hot path.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from backend.database import Base


class RankSnapshot(Base):
    __tablename__ = "rank_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    leaderboard_id = Column(
        String(100),
        ForeignKey("leaderboards.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    rank = Column(Integer, nullable=False)
    score = Column(Numeric(10, 2), nullable=False)
    snapshotted_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_rank_snapshots_user_lb_time",
            "user_id",
            "leaderboard_id",
            "snapshotted_at",
        ),
    )
