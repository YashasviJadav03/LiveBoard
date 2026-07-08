# Sprint 3: Segments & Advanced Scoring

## Goal
Expand the leaderboard functionality to support multiple segments (all-time, daily, weekly, regional) and robust tie-breaking mechanisms.

## Key Accomplishments
- **Multiple Segments**: Implemented segmented leaderboards.
- **Redis Key Schema**: Designed the Redis key schema for different time horizons and regional segments (e.g., `lb:{id}:all`, `lb:{id}:day:{date}`).
- **Composite Scoring**: Developed a composite score algorithm (`score + time-based fractional part`) to enable deterministic FIFO tie-breaking without secondary sorts.
- **Rate Limiting**: Implemented a Redis-based atomic `INCR + EXPIRE` mechanism to limit users to 10 score updates per minute.
- **Testing**: Developed comprehensive test suite (`test_phase3_segments.py`) to verify multi-segment updates and strict tie-breaker handling.

## Deliverables
- Advanced segment routing and scoring logic in `backend/routers/scores.py` and `backend/routers/leaderboard.py`.
- Segment-specific test suite.
