"""Score update endpoints — Phase 4: Segmented writes + WebSocket push."""

import logging
import os
import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.connection_manager import manager
from backend.database import get_db
from backend.models.user import ScoreEvent, User
from backend.redis_client import get_redis
from backend.schemas.score import LegacyScoreSubmit, ScoreUpdateResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scores", tags=["scores"])


# ── Composite-score helpers ──────────────────────────────────

TIEBREAK_SCALE = 1e10

# TTLs for time-windowed segments (seconds)
DAILY_TTL = 172800    # 2 days
WEEKLY_TTL = 691200   # 8 days

# Rate limiting — configurable via env for load testing
RATE_LIMIT_MAX = int(os.environ.get("RATE_LIMIT_MAX", "10"))
RATE_LIMIT_WINDOW = 60    # per 60-second window


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


# ── Redis key resolver ───────────────────────────────────────

def resolve_redis_key(
    lb_id: str,
    segment: str,
    region: str | None = None,
) -> str:
    """Map a segment name to the correct Redis sorted-set key.

    Parameters
    ----------
    lb_id : str
        Leaderboard identifier.
    segment : str
        One of ``all_time``, ``daily``, ``weekly``, ``regional``.
    region : str | None
        Required when *segment* is ``regional``.

    Returns
    -------
    str
        The fully-qualified Redis key.

    Raises
    ------
    ValueError
        If *segment* is ``regional`` but *region* was not supplied,
        or if *segment* is unknown.
    """
    now = datetime.now(timezone.utc)

    if segment == "all_time":
        return f"lb:{lb_id}:all"
    elif segment == "daily":
        return f"lb:{lb_id}:day:{now.strftime('%Y-%m-%d')}"
    elif segment == "weekly":
        return f"lb:{lb_id}:week:{now.strftime('%Y-W%W')}"
    elif segment == "regional":
        if not region:
            raise ValueError("region is required for the regional segment")
        return f"lb:{lb_id}:region:{region}"
    else:
        raise ValueError(f"Unknown segment: {segment}")


def _build_all_segment_keys(lb_id: str, user_region: str | None) -> list[str]:
    """Return the list of Redis keys that a single score update must touch.

    Always includes all-time, daily, and weekly.
    Regional is included only when *user_region* is set.
    """
    now = datetime.now(timezone.utc)
    keys = [
        f"lb:{lb_id}:all",
        f"lb:{lb_id}:day:{now.strftime('%Y-%m-%d')}",
        f"lb:{lb_id}:week:{now.strftime('%Y-W%W')}",
    ]
    if user_region:
        keys.append(f"lb:{lb_id}:region:{user_region}")
    return keys


# ── WebSocket push notifications (Phase 4) ───────────────────

async def _push_score_notifications(
    lb_id: str,
    user_key: str,
    username: str | None,
    new_score: float,
    previous_rank: int | None,
    new_rank: int,
    redis,
) -> None:
    """Push WebSocket notifications after a score update.

    Three notification types:

    1. **rank_change** — sent to the scoring user if their rank actually
       changed (and they had a previous rank).
    2. **leaderboard_update** — broadcast to all leaderboard viewers if
       the scoring user is now in the top 10.
    3. **displaced** — sent to the user who was pushed down from the rank
       the scoring user just moved into.

    All sends are no-ops if the target user is not connected.
    """
    redis_key = f"lb:{lb_id}:all"
    rank_changed = previous_rank is None or previous_rank != new_rank
    moved_up = previous_rank is None or new_rank < previous_rank

    # ── Batch-fetch extra data from Redis (single pipeline) ───
    need_top10 = new_rank <= 10
    need_displaced = rank_changed and moved_up

    pipe_cmds: list[str] = []
    if need_top10 or need_displaced:
        pipe = redis.pipeline(transaction=True)
        if need_top10:
            pipe.zrevrange(redis_key, 0, 9, withscores=True)
            pipe_cmds.append("top10")
        if need_displaced:
            pipe.zrevrange(redis_key, new_rank, new_rank)
            pipe_cmds.append("displaced")
        pipe_results = await pipe.execute()
    else:
        pipe_results = []

    # Unpack pipeline results by command label
    result_map: dict[str, list] = {}
    for i, cmd in enumerate(pipe_cmds):
        result_map[cmd] = pipe_results[i]

    # ── 1. Rank change notification ───────────────────────────
    if previous_rank is not None and previous_rank != new_rank:
        await manager.send_to_user(lb_id, user_key, {
            "type": "rank_change",
            "user_id": user_key,
            "previous_rank": previous_rank,
            "new_rank": new_rank,
            "score": new_score,
            "message": f"You moved from #{previous_rank} to #{new_rank}! \U0001f389",
        })

    # ── 2. Top-10 broadcast ──────────────────────────────────
    if need_top10 and "top10" in result_map:
        top10_raw = result_map["top10"]
        top10 = [
            {
                "rank": i + 1,
                "user_id": member,
                "score": extract_actual_score(comp),
            }
            for i, (member, comp) in enumerate(top10_raw)
        ]
        await manager.broadcast_to_leaderboard(lb_id, {
            "type": "leaderboard_update",
            "lb_id": lb_id,
            "segment": "all_time",
            "top10": top10,
        })

    # ── 3. Displacement notification ─────────────────────────
    if need_displaced and "displaced" in result_map:
        displaced_raw = result_map["displaced"]
        if displaced_raw:
            displaced_uid = displaced_raw[0]
            if displaced_uid != user_key:
                await manager.send_to_user(lb_id, displaced_uid, {
                    "type": "displaced",
                    "previous_rank": new_rank,
                    "new_rank": new_rank + 1,
                    "displaced_by": username or user_key,
                })


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
    """Core score-update logic — writes to ALL segment keys.

    0. Rate-limit check (max 10 updates per user per minute).
    1. Verify the user exists in PostgreSQL (also fetches region).
    2. Build segment keys (all-time, daily, weekly, regional).
    3. Pipeline-read previous composite scores + all-time rank.
    4. Compute new composite scores for every segment.
    5. Pipeline-write all ZADD + EXPIRE (daily/weekly) + ZREVRANK.
    6. Insert a score_events row into PostgreSQL.
    7. Return the full rank-change response.
    """
    user_key = str(user_id)
    now_ts = time.time()

    # ── 0. Rate-limit check ───────────────────────────────────
    rl_key = f"ratelimit:{user_key}:{int(now_ts) // 60}"
    pipe_rl = redis.pipeline(transaction=True)
    pipe_rl.incr(rl_key)
    pipe_rl.expire(rl_key, RATE_LIMIT_WINDOW)
    rl_count, _ = await pipe_rl.execute()
    if rl_count > RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded — max {RATE_LIMIT_MAX} score updates per minute",
        )

    # ── 1. Verify user + fetch region ─────────────────────────
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ── 2. Build segment keys ─────────────────────────────────
    segment_keys = _build_all_segment_keys(lb_id, user.region)
    all_key = segment_keys[0]       # always "lb:{lb_id}:all"
    day_key = segment_keys[1]       # "lb:{lb_id}:day:YYYY-MM-DD"
    week_key = segment_keys[2]      # "lb:{lb_id}:week:YYYY-Www"

    # ── 3. Pipeline-read previous state ───────────────────────
    pipe_read = redis.pipeline(transaction=True)
    for key in segment_keys:
        pipe_read.zscore(key, user_key)
    pipe_read.zrevrank(all_key, user_key)   # previous all-time rank
    read_results = await pipe_read.execute()

    prev_composites = read_results[: len(segment_keys)]
    prev_rank_raw = read_results[len(segment_keys)]

    # Extract the all-time actual score for the response
    prev_actual_all = (
        extract_actual_score(prev_composites[0])
        if prev_composites[0] is not None
        else 0.0
    )
    previous_rank = (prev_rank_raw + 1) if prev_rank_raw is not None else None

    # ── 4. Compute new composite for each segment ─────────────
    new_composites: list[float] = []
    new_actual_all = 0.0
    for idx, prev_comp in enumerate(prev_composites):
        prev_actual = (
            extract_actual_score(prev_comp) if prev_comp is not None else 0.0
        )
        new_actual = prev_actual + delta
        new_comp = composite_score(new_actual, now_ts)
        new_composites.append(new_comp)
        if idx == 0:
            new_actual_all = new_actual  # capture all-time actual for response

    # ── 5. Pipeline-write all segments atomically ─────────────
    pipe_write = redis.pipeline(transaction=True)
    for key, comp in zip(segment_keys, new_composites):
        pipe_write.zadd(key, {user_key: comp})

    # TTLs for time-windowed keys
    pipe_write.expire(day_key, DAILY_TTL)
    pipe_write.expire(week_key, WEEKLY_TTL)

    # Read new all-time rank
    pipe_write.zrevrank(all_key, user_key)
    write_results = await pipe_write.execute()

    # ZREVRANK result is the last item in the pipeline
    new_rank_0 = write_results[-1]
    new_rank = new_rank_0 + 1  # 1-indexed

    # ── 6. Persist to PostgreSQL ──────────────────────────────
    event = ScoreEvent(
        user_id=user_id,
        leaderboard_id=lb_id,
        score_delta=delta,
        total_score_after=new_actual_all,
        rank_after=new_rank,
        source="api",
    )
    db.add(event)
    await db.flush()

    # ── 7. Build response ─────────────────────────────────────
    rank_change = (previous_rank - new_rank) if previous_rank is not None else None

    response = ScoreUpdateResponse(
        user_id=user_id,
        new_score=new_actual_all,
        new_rank=new_rank,
        previous_rank=previous_rank,
        rank_change=rank_change,
    )

    # ── 8. Push WebSocket notifications (Phase 4) ─────────────
    try:
        await _push_score_notifications(
            lb_id=lb_id,
            user_key=user_key,
            username=user.username,
            new_score=new_actual_all,
            previous_rank=previous_rank,
            new_rank=new_rank,
            redis=redis,
        )
    except Exception:
        logger.warning(
            "Failed to push WS notifications for lb=%s user=%s",
            lb_id, user_key, exc_info=True,
        )

    return response
