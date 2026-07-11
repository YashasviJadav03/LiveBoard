"""Pydantic schemas for scores, users, leaderboards, and API responses."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── User schemas ──────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=50)
    avatar_url: Optional[str] = None


class UserResponse(BaseModel):
    id: UUID
    username: str
    display_name: Optional[str] = None
    region: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Leaderboard CRUD schemas ─────────────────────────────────

class LeaderboardCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None


class LeaderboardMeta(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_active: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Segment enum ─────────────────────────────────────────────

class SegmentType(str, Enum):
    """Leaderboard time/scope segments."""
    all_time = "all_time"
    daily = "daily"
    weekly = "weekly"
    regional = "regional"


# ── Score update schemas ─────────────────────────────────────

class ScoreSubmit(BaseModel):
    """Body for POST /leaderboards/{lb_id}/scores."""
    user_id: UUID
    delta: int = Field(..., description="Points to add to the user's score")


class LegacyScoreSubmit(BaseModel):
    """Body for legacy POST /scores/{user_id} endpoint."""
    leaderboard_id: str = Field(..., min_length=1, max_length=100)
    score_delta: int = Field(..., description="Points to add to the user's score")


class ScoreUpdateResponse(BaseModel):
    """Returned after a score update — includes rank change info."""
    user_id: UUID
    new_score: int
    new_rank: int
    previous_rank: Optional[int] = None
    rank_change: Optional[int] = None


# ── Rank / Surrounding schemas ───────────────────────────────

class SurroundingEntry(BaseModel):
    rank: int
    user_id: str
    username: Optional[str] = None
    score: int


class UserRankResponse(BaseModel):
    rank: int
    score: int
    username: Optional[str] = None
    display_name: Optional[str] = None
    surrounding: list[SurroundingEntry] = []


# ── Paginated top-N schemas ──────────────────────────────────

class TopEntry(BaseModel):
    rank: int
    user_id: str
    username: Optional[str] = None
    score: int


class TopLeaderboardResponse(BaseModel):
    total_users: int
    page: int
    limit: int
    segment: str = "all_time"
    entries: list[TopEntry] = []


# ── Friends leaderboard schemas (Phase 3) ────────────────────

class FriendEntry(BaseModel):
    rank: int
    user_id: str
    username: Optional[str] = None
    score: int


class FriendsLeaderboardResponse(BaseModel):
    leaderboard_id: str
    user_id: str
    total_friends: int
    limit: int
    entries: list[FriendEntry] = []


# ── Segments listing schemas (Phase 3) ───────────────────────

class SegmentInfo(BaseModel):
    segment: str
    redis_key: str
    member_count: int


class SegmentsResponse(BaseModel):
    leaderboard_id: str
    segments: list[SegmentInfo] = []


# ── Legacy leaderboard response (kept for backward compat) ───

class LeaderboardEntry(BaseModel):
    user_id: UUID
    username: str
    total_score: Decimal
    rank: int


class LeaderboardResponse(BaseModel):
    leaderboard_id: str
    entries: list[LeaderboardEntry]
    total: int


# ── Legacy score event response ──────────────────────────────

class ScoreEventResponse(BaseModel):
    id: UUID
    user_id: UUID
    leaderboard_id: str
    score_delta: Decimal
    total_score: Decimal
    recorded_at: datetime

    model_config = {"from_attributes": True}


# ── Health schema ─────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    redis: str
    db: str


# ── Friendship schema ────────────────────────────────────────

class FriendshipResponse(BaseModel):
    user_id: UUID
    friend_id: UUID
    message: str


# ── Score history schemas (Phase 5) ──────────────────────────

class ScoreHistoryEntry(BaseModel):
    """Single data-point for the score-over-time chart."""
    recorded_at: datetime
    score_delta: int
    total_score: int


class ScoreHistoryResponse(BaseModel):
    user_id: str
    leaderboard_id: str
    entries: list[ScoreHistoryEntry] = []


