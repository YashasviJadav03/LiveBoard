"""SQLAlchemy models — User, Friendship, ScoreEvent."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(100), nullable=True)
    region = Column(String(50), nullable=True)
    avatar_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # relationships
    score_events = relationship("ScoreEvent", back_populates="user", lazy="selectin")
    friends = relationship(
        "User",
        secondary="friendships",
        primaryjoin="User.id == Friendship.user_id",
        secondaryjoin="User.id == Friendship.friend_id",
        lazy="selectin",
    )


class Friendship(Base):
    __tablename__ = "friendships"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    friend_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "friend_id", name="uq_friendship"),
        Index("idx_friendships_user", "user_id"),
    )


class ScoreEvent(Base):
    __tablename__ = "score_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    leaderboard_id = Column(String(100), ForeignKey("leaderboards.id", ondelete="CASCADE"), nullable=False)
    score_delta = Column(Numeric(10, 2), nullable=False)
    total_score_after = Column(Numeric(10, 2), nullable=False)
    rank_after = Column(Integer, nullable=True)
    source = Column(String(50), nullable=True, default="api")
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # relationships
    user = relationship("User", back_populates="score_events")

    __table_args__ = (
        Index("idx_score_events_user_lb", "user_id", "leaderboard_id"),
        Index("idx_score_events_time", "recorded_at"),
        Index("idx_score_events_lb_time", "leaderboard_id", "recorded_at"),
    )
