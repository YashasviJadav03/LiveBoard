import { useEffect, useState } from 'react';
import { getUserRank } from '../api';

export default function MyRank({ lbId, userId, wsMessage }) {
  const [rankData, setRankData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchRank = async () => {
    if (!lbId || !userId) return;
    setLoading(true);
    try {
      const res = await getUserRank(lbId, userId);
      setRankData(res.data);
    } catch (err) {
      // User may not have a score yet
      setRankData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRank();
  }, [lbId, userId]);

  // Refresh when we receive a rank-affecting WS message
  useEffect(() => {
    if (!wsMessage) return;
    if (['rank_change', 'leaderboard_update', 'displaced'].includes(wsMessage.type)) {
      fetchRank();
    }
  }, [wsMessage]);

  if (loading && !rankData) {
    return (
      <div className="card">
        <div className="card-header"><span className="card-title">📍 My Rank</span></div>
        <div className="loading"><div className="spinner" />Loading...</div>
      </div>
    );
  }

  if (!rankData) {
    return (
      <div className="card">
        <div className="card-header"><span className="card-title">📍 My Rank</span></div>
        <div className="card-body" style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px' }}>
          No rank yet. Submit a score to get started!
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header"><span className="card-title">📍 My Rank</span></div>

      <div className="my-rank-hero">
        <div className="my-rank-number">#{rankData.rank}</div>
        <div className="my-rank-label">{rankData.username || 'You'}</div>
        <div className="my-rank-score">{Number(rankData.score).toLocaleString()} pts</div>
      </div>

      {rankData.surrounding && rankData.surrounding.length > 0 && (
        <ul className="surrounding-list">
          {/* Users above */}
          {rankData.surrounding
            .filter((s) => s.rank < rankData.rank)
            .sort((a, b) => a.rank - b.rank)
            .map((s) => (
              <li key={s.user_id} className="surrounding-item">
                <span className="surrounding-rank">#{s.rank}</span>
                <span className="surrounding-name">{s.username || s.user_id.slice(0, 8)}</span>
                <span className="surrounding-score">{Number(s.score).toLocaleString()}</span>
              </li>
            ))}

          {/* Current user */}
          <li className="surrounding-item is-me">
            <span className="surrounding-rank">#{rankData.rank}</span>
            <span className="surrounding-name" style={{ fontWeight: 700 }}>
              {rankData.username || 'You'} ← You
            </span>
            <span className="surrounding-score">{Number(rankData.score).toLocaleString()}</span>
          </li>

          {/* Users below */}
          {rankData.surrounding
            .filter((s) => s.rank > rankData.rank)
            .sort((a, b) => a.rank - b.rank)
            .map((s) => (
              <li key={s.user_id} className="surrounding-item">
                <span className="surrounding-rank">#{s.rank}</span>
                <span className="surrounding-name">{s.username || s.user_id.slice(0, 8)}</span>
                <span className="surrounding-score">{Number(s.score).toLocaleString()}</span>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
