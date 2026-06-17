"""SQLAlchemy model — Leaderboard."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text

from backend.database import Base


class Leaderboard(Base):
    __tablename__ = "leaderboards"

    id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
