"""Pydantic schemas for scores, users, and API responses."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── User schemas ──────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=50)


class UserResponse(BaseModel):
    id: UUID
    username: str
    display_name: Optional[str] = None
    region: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Score schemas ─────────────────────────────────────────────

class ScoreSubmit(BaseModel):
    leaderboard_id: str = Field(..., min_length=1, max_length=100)
    score_delta: Decimal = Field(..., decimal_places=2)


class ScoreEventResponse(BaseModel):
    id: UUID
    user_id: UUID
    leaderboard_id: str
    score_delta: Decimal
    total_score: Decimal
    recorded_at: datetime

    model_config = {"from_attributes": True}


# ── Leaderboard schemas ──────────────────────────────────────

class LeaderboardEntry(BaseModel):
    user_id: UUID
    username: str
    total_score: Decimal
    rank: int


class LeaderboardResponse(BaseModel):
    leaderboard_id: str
    entries: list[LeaderboardEntry]
    total: int


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
