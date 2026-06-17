"""Leaderboard CRUD + rank-query endpoints — Phase 2: Core Ranking Engine."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.leaderboard import Leaderboard
from backend.models.user import User
from backend.redis_client import get_redis
from backend.routers.scores import (
    _submit_score,
    extract_actual_score,
)
from backend.schemas.score import (
    LeaderboardCreate,
    LeaderboardMeta,
    ScoreSubmit,
    ScoreUpdateResponse,
    SurroundingEntry,
    TopEntry,
    TopLeaderboardResponse,
    UserRankResponse,
)

router = APIRouter(prefix="/leaderboards", tags=["leaderboards"])


# ── Helper: resolve user_ids → usernames in batch ────────────

async def _resolve_usernames(
    user_ids: list[str], db: AsyncSession
) -> dict[str, tuple[str | None, str | None]]:
    """Return {str(user_id): (username, display_name)} for a list of user IDs.

    Invalid UUIDs are silently skipped.
    """
    if not user_ids:
        return {}

    valid_uuids: list[UUID] = []
    for uid in user_ids:
        try:
            valid_uuids.append(UUID(uid))
        except ValueError:
            continue

    if not valid_uuids:
        return {}

    result = await db.execute(
        select(User.id, User.username, User.display_name).where(User.id.in_(valid_uuids))
    )
    rows = result.all()
    return {str(r.id): (r.username, r.display_name) for r in rows}


# ──────────────────────────────────────────────────────────────
# 1. POST /leaderboards — create a leaderboard
# ──────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=LeaderboardMeta,
    status_code=status.HTTP_201_CREATED,
)
async def create_leaderboard(
    payload: LeaderboardCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new leaderboard. Stores metadata in PostgreSQL only — no Redis op."""
    existing = await db.get(Leaderboard, payload.id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Leaderboard '{payload.id}' already exists",
        )

    lb = Leaderboard(
        id=payload.id,
        name=payload.name,
        description=payload.description,
    )
    db.add(lb)
    await db.flush()
    await db.refresh(lb)
    return lb


# ──────────────────────────────────────────────────────────────
# 2. POST /leaderboards/{lb_id}/scores — submit score delta
# ──────────────────────────────────────────────────────────────

@router.post(
    "/{lb_id}/scores",
    response_model=ScoreUpdateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_score(
    lb_id: str,
    payload: ScoreSubmit,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Update a user's score on a leaderboard.

    - ZADD composite score to Redis for tie-breaking
    - Insert audit row into score_events
    - Return rank change info
    """
    # verify leaderboard exists
    lb = await db.get(Leaderboard, lb_id)
    if not lb:
        raise HTTPException(status_code=404, detail=f"Leaderboard '{lb_id}' not found")

    return await _submit_score(
        lb_id=lb_id,
        user_id=payload.user_id,
        delta=payload.delta,
        db=db,
        redis=redis,
    )


# ──────────────────────────────────────────────────────────────
# 3. GET /leaderboards/{lb_id}/rank/{user_id}
# ──────────────────────────────────────────────────────────────

@router.get(
    "/{lb_id}/rank/{user_id}",
    response_model=UserRankResponse,
)
async def get_user_rank(
    lb_id: str,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Return a user's rank, score, and the 3 users above & 3 below them."""
    redis_key = f"lb:{lb_id}:all"
    user_key = str(user_id)

    # ── 1. Get the user's rank and score (pipelined) ──────────
    pipe = redis.pipeline(transaction=True)
    pipe.zrevrank(redis_key, user_key)
    pipe.zscore(redis_key, user_key)
    rank_0, composite = await pipe.execute()

    if rank_0 is None:
        raise HTTPException(
            status_code=404,
            detail=f"User {user_id} not found on leaderboard '{lb_id}'",
        )

    rank = rank_0 + 1  # 1-indexed
    actual_score = extract_actual_score(composite)

    # ── 2. Get surrounding users (3 above, 3 below) ──────────
    # "3 above" means ranks rank-3 .. rank-1  → 0-indexed: rank_0-3 .. rank_0-1
    # "3 below" means ranks rank+1 .. rank+3  → 0-indexed: rank_0+1 .. rank_0+3
    start_above = max(0, rank_0 - 3)
    end_below = rank_0 + 3

    # ZREVRANGE returns members ordered by descending score
    surrounding_raw = await redis.zrevrange(
        redis_key, start_above, end_below, withscores=True
    )

    # Collect user IDs for batch username resolution
    surrounding_user_ids = [member for member, _score in surrounding_raw if member != user_key]
    all_user_ids = surrounding_user_ids + [user_key]
    username_map = await _resolve_usernames(all_user_ids, db)

    surrounding: list[SurroundingEntry] = []
    for idx, (member, comp_score) in enumerate(surrounding_raw):
        member_rank = start_above + idx + 1  # 1-indexed
        if member == user_key:
            continue  # skip the user themselves
        uname, _ = username_map.get(member, (None, None))
        surrounding.append(
            SurroundingEntry(
                rank=member_rank,
                user_id=member,
                username=uname,
                score=extract_actual_score(comp_score),
            )
        )

    # ── 3. Resolve requesting user's info ─────────────────────
    req_uname, req_display = username_map.get(user_key, (None, None))

    return UserRankResponse(
        rank=rank,
        score=actual_score,
        username=req_uname,
        display_name=req_display,
        surrounding=surrounding,
    )


# ──────────────────────────────────────────────────────────────
# 4. GET /leaderboards/{lb_id}/top?limit=50&page=1
# ──────────────────────────────────────────────────────────────

@router.get(
    "/{lb_id}/top",
    response_model=TopLeaderboardResponse,
)
async def get_top(
    lb_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    page: int = Query(default=1, ge=1),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Paginated top-N leaderboard using ZREVRANGE with offset."""
    redis_key = f"lb:{lb_id}:all"
    offset = (page - 1) * limit

    # ── Pipelined: get page + total count ─────────────────────
    pipe = redis.pipeline(transaction=True)
    pipe.zrevrange(redis_key, offset, offset + limit - 1, withscores=True)
    pipe.zcard(redis_key)
    page_data, total_users = await pipe.execute()

    # ── Resolve usernames in batch ────────────────────────────
    user_ids = [member for member, _score in page_data]
    username_map = await _resolve_usernames(user_ids, db)

    entries: list[TopEntry] = []
    for idx, (member, comp_score) in enumerate(page_data):
        uname, _ = username_map.get(member, (None, None))
        entries.append(
            TopEntry(
                rank=offset + idx + 1,  # 1-indexed
                user_id=member,
                username=uname,
                score=extract_actual_score(comp_score),
            )
        )

    return TopLeaderboardResponse(
        total_users=total_users,
        page=page,
        limit=limit,
        entries=entries,
    )
