"""Leaderboard CRUD + rank/segment query endpoints — Phase 3+5."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.leaderboard import Leaderboard
from backend.models.user import Friendship, ScoreEvent, User
from backend.redis_client import get_redis
from backend.routers.scores import (
    _submit_score,
    extract_actual_score,
    resolve_redis_key,
)
from backend.schemas.score import (
    FriendEntry,
    FriendsLeaderboardResponse,
    LeaderboardCreate,
    LeaderboardMeta,
    ScoreHistoryEntry,
    ScoreHistoryResponse,
    ScoreSubmit,
    ScoreUpdateResponse,
    SegmentInfo,
    SegmentType,
    SegmentsResponse,
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
#    (Phase 3: now writes to all 4 segment keys atomically)
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

    Writes composite scores to all segment keys (all-time, daily, weekly,
    regional) in a single Redis pipeline.
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
    segment: SegmentType = Query(default=SegmentType.all_time),
    region: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Return a user's rank, score, and the 3 users above & 3 below them.

    Supports all segment types via the ``segment`` query parameter.
    """
    if segment == SegmentType.regional and not region:
        raise HTTPException(
            status_code=400,
            detail="'region' query parameter is required when segment=regional",
        )

    redis_key = resolve_redis_key(lb_id, segment.value, region)
    user_key = str(user_id)

    # ── 1. Get the user's rank and score (pipelined) ──────────
    pipe = redis.pipeline(transaction=True)
    pipe.zrevrank(redis_key, user_key)
    pipe.zscore(redis_key, user_key)
    rank_0, composite = await pipe.execute()

    if rank_0 is None:
        raise HTTPException(
            status_code=404,
            detail=f"User {user_id} not found on leaderboard '{lb_id}' segment '{segment.value}'",
        )

    rank = rank_0 + 1  # 1-indexed
    actual_score = extract_actual_score(composite)

    # ── 2. Get surrounding users (3 above, 3 below) ──────────
    start_above = max(0, rank_0 - 3)
    end_below = rank_0 + 3

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
# 4. GET /leaderboards/{lb_id}/top?segment=all_time&limit=50&page=1
#    (Phase 3: now accepts segment query parameter)
# ──────────────────────────────────────────────────────────────

@router.get(
    "/{lb_id}/top",
    response_model=TopLeaderboardResponse,
)
async def get_top(
    lb_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    page: int = Query(default=1, ge=1),
    segment: SegmentType = Query(default=SegmentType.all_time),
    region: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Paginated top-N leaderboard using ZREVRANGE with offset.

    Set ``segment`` to ``daily``, ``weekly``, ``regional``, or ``all_time``
    (the default) to query different time/scope windows.
    For ``regional``, the ``region`` query parameter is required.
    """
    if segment == SegmentType.regional and not region:
        raise HTTPException(
            status_code=400,
            detail="'region' query parameter is required when segment=regional",
        )

    redis_key = resolve_redis_key(lb_id, segment.value, region)
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
        segment=segment.value,
        entries=entries,
    )


# ──────────────────────────────────────────────────────────────
# 5. GET /leaderboards/{lb_id}/friends/{user_id}/top — Phase 3
# ──────────────────────────────────────────────────────────────

@router.get(
    "/{lb_id}/friends/{user_id}/top",
    response_model=FriendsLeaderboardResponse,
)
async def get_friends_top(
    lb_id: str,
    user_id: UUID,
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """Friends leaderboard — computed dynamically.

    1. Fetch friend IDs from the ``friendships`` table.
    2. Include the requesting user themselves.
    3. Batch-fetch scores from Redis via pipeline ZSCORE.
    4. Sort descending, return top *limit* entries with friend-group rank.
    """
    user_key = str(user_id)
    redis_key = f"lb:{lb_id}:all"

    # ── 1. Verify the requesting user exists ──────────────────
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ── 2. Get friend IDs from PostgreSQL ─────────────────────
    result = await db.execute(
        select(Friendship.friend_id).where(Friendship.user_id == user_id)
    )
    friend_rows = result.all()
    member_ids = [str(row.friend_id) for row in friend_rows] + [user_key]

    # ── 3. Batch-fetch scores from Redis (pipelined) ──────────
    pipe = redis.pipeline(transaction=True)
    for uid in member_ids:
        pipe.zscore(redis_key, uid)
    scores = await pipe.execute()

    # ── 4. Pair up, filter out None (users with no score) ─────
    scored_members = [
        (uid, comp_score)
        for uid, comp_score in zip(member_ids, scores)
        if comp_score is not None
    ]

    # ── 5. Sort by composite score descending ─────────────────
    scored_members.sort(key=lambda x: x[1], reverse=True)

    # ── 6. Take top N ─────────────────────────────────────────
    top_members = scored_members[:limit]

    # ── 7. Resolve usernames in batch ─────────────────────────
    top_user_ids = [uid for uid, _ in top_members]
    username_map = await _resolve_usernames(top_user_ids, db)

    entries: list[FriendEntry] = []
    for rank_idx, (uid, comp_score) in enumerate(top_members):
        uname, _ = username_map.get(uid, (None, None))
        entries.append(
            FriendEntry(
                rank=rank_idx + 1,
                user_id=uid,
                username=uname,
                score=extract_actual_score(comp_score),
            )
        )

    return FriendsLeaderboardResponse(
        leaderboard_id=lb_id,
        user_id=user_key,
        total_friends=len(scored_members),
        limit=limit,
        entries=entries,
    )


# ──────────────────────────────────────────────────────────────
# 6. GET /leaderboards/{lb_id}/segments — Phase 3
# ──────────────────────────────────────────────────────────────

@router.get(
    "/{lb_id}/segments",
    response_model=SegmentsResponse,
)
async def get_segments(
    lb_id: str,
    redis=Depends(get_redis),
):
    """List available segments for this leaderboard with member counts.

    Returns the known segment types (all-time, daily, weekly) plus any
    regional segments discovered via ``KEYS lb:{lb_id}:region:*``.
    """
    now = datetime.now(timezone.utc)

    # ── Fixed segments ────────────────────────────────────────
    fixed_segments: list[tuple[str, str]] = [
        ("all_time", f"lb:{lb_id}:all"),
        ("daily", f"lb:{lb_id}:day:{now.strftime('%Y-%m-%d')}"),
        ("weekly", f"lb:{lb_id}:week:{now.strftime('%Y-W%W')}"),
    ]

    # ── Discover regional segments dynamically ────────────────
    region_keys: list[str] = await redis.keys(f"lb:{lb_id}:region:*")
    for rk in sorted(region_keys):
        region_name = rk.split(":")[-1]
        fixed_segments.append((f"regional:{region_name}", rk))

    # ── Batch ZCARD for all keys ──────────────────────────────
    pipe = redis.pipeline(transaction=True)
    for _, key in fixed_segments:
        pipe.zcard(key)
    counts = await pipe.execute()

    segment_infos: list[SegmentInfo] = []
    for (seg_name, redis_key), count in zip(fixed_segments, counts):
        segment_infos.append(
            SegmentInfo(
                segment=seg_name,
                redis_key=redis_key,
                member_count=count,
            )
        )

    return SegmentsResponse(
        leaderboard_id=lb_id,
        segments=segment_infos,
    )


# ──────────────────────────────────────────────────────────────
# 7. GET /leaderboards/{lb_id}/users/{user_id}/history — Phase 5
# ──────────────────────────────────────────────────────────────

@router.get(
    "/{lb_id}/users/{user_id}/history",
    response_model=ScoreHistoryResponse,
)
async def get_score_history(
    lb_id: str,
    user_id: UUID,
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's score-over-time for the given leaderboard.

    Queries the ``score_events`` table and returns entries ordered by time,
    suitable for rendering in a Recharts LineChart.
    """
    result = await db.execute(
        select(ScoreEvent)
        .where(
            ScoreEvent.user_id == user_id,
            ScoreEvent.leaderboard_id == lb_id,
        )
        .order_by(ScoreEvent.recorded_at.asc())
        .limit(limit)
    )
    events = result.scalars().all()

    entries = [
        ScoreHistoryEntry(
            recorded_at=e.recorded_at,
            score_delta=float(e.score_delta),
            total_score=float(e.total_score_after),
        )
        for e in events
    ]

    return ScoreHistoryResponse(
        user_id=str(user_id),
        leaderboard_id=lb_id,
        entries=entries,
    )
