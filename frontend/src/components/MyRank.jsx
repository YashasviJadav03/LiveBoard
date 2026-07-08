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
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between"><span className="text-sm font-bold uppercase tracking-[0.5px] text-text-secondary">📍 My Rank</span></div>
        <div className="flex items-center justify-center p-10 text-muted text-sm gap-2.5"><div className="w-[18px] h-[18px] border-2 border-border border-t-accent rounded-full animate-spin" />Loading...</div>
      </div>
    );
  }

  if (!rankData) {
    return (
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between"><span className="text-sm font-bold uppercase tracking-[0.5px] text-text-secondary">📍 My Rank</span></div>
        <div className="text-center text-muted p-6 text-sm">
          No rank yet. Submit a score to get started!
        </div>
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between"><span className="text-sm font-bold uppercase tracking-[0.5px] text-text-secondary">📍 My Rank</span></div>

      <div className="text-center px-4 py-6">
        <div className="text-[52px] font-extrabold leading-none bg-gradient-to-br from-accent to-[#a78bfa] bg-clip-text text-transparent">#{rankData.rank}</div>
        <div className="text-[13px] text-muted mt-1">{rankData.username || 'You'}</div>
        <div className="text-xl font-bold text-green mt-2">{Number(rankData.score).toLocaleString()} pts</div>
      </div>

      {rankData.surrounding && rankData.surrounding.length > 0 && (
        <ul className="list-none m-0 p-0">
          {/* Users above */}
          {rankData.surrounding
            .filter((s) => s.rank < rankData.rank)
            .sort((a, b) => a.rank - b.rank)
            .map((s) => (
              <li key={s.user_id} className="flex items-center gap-3 px-5 py-2.5 border-b border-[#2a335480] text-sm transition-colors hover:bg-card-hover">
                <span className="w-7 font-bold text-muted text-center">#{s.rank}</span>
                <span className="flex-1 font-medium">{s.username || s.user_id.slice(0, 8)}</span>
                <span className="font-semibold tabular-nums text-accent-hover">{Number(s.score).toLocaleString()}</span>
              </li>
            ))}

          {/* Current user */}
          <li className="flex items-center gap-3 px-5 py-2.5 border-b border-[#2a335480] text-sm transition-colors bg-[rgba(99,102,241,0.08)] border-l-4 border-l-accent hover:bg-card-hover">
            <span className="w-7 font-bold text-muted text-center">#{rankData.rank}</span>
            <span className="flex-1 font-bold">
              {rankData.username || 'You'} <span className="text-accent text-[11px] ml-1">← YOU</span>
            </span>
            <span className="font-semibold tabular-nums text-accent-hover">{Number(rankData.score).toLocaleString()}</span>
          </li>

          {/* Users below */}
          {rankData.surrounding
            .filter((s) => s.rank > rankData.rank)
            .sort((a, b) => a.rank - b.rank)
            .map((s) => (
              <li key={s.user_id} className="flex items-center gap-3 px-5 py-2.5 border-b border-[#2a335480] text-sm transition-colors hover:bg-card-hover">
                <span className="w-7 font-bold text-muted text-center">#{s.rank}</span>
                <span className="flex-1 font-medium">{s.username || s.user_id.slice(0, 8)}</span>
                <span className="font-semibold tabular-nums text-accent-hover">{Number(s.score).toLocaleString()}</span>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
