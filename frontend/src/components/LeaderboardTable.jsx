import { useEffect, useState, useRef } from 'react';
import { getTop, getFriendsTop } from '../api';

const SEGMENTS = [
  { key: 'all_time', label: 'All Time' },
  { key: 'daily', label: 'Daily' },
  { key: 'weekly', label: 'Weekly' },
  { key: 'regional', label: 'Regional' },
  { key: 'friends', label: 'Friends' },
];

function RankBadge({ rank }) {
  let cls = 'bg-primary text-text-secondary border border-border';
  if (rank === 1) cls = 'bg-gradient-to-br from-gold to-[#d97706] text-[#1a1a1a] border-none';
  else if (rank === 2) cls = 'bg-gradient-to-br from-silver to-[#64748b] text-[#1a1a1a] border-none';
  else if (rank === 3) cls = 'bg-gradient-to-br from-bronze to-[#b45309] text-[#1a1a1a] border-none';
  return <span className={`inline-flex items-center justify-center w-8 h-8 rounded-lg font-extrabold text-sm ${cls}`}>{rank}</span>;
}

export default function LeaderboardTable({ lbId, userId, wsMessage, region }) {
  const [segment, setSegment] = useState('all_time');
  const [entries, setEntries] = useState([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [flashRows, setFlashRows] = useState({}); // userId -> 'rank-up' | 'rank-down'
  const prevEntriesRef = useRef([]);
  const limit = 50;

  // Fetch leaderboard data
  const fetchData = async () => {
    setLoading(true);
    try {
      let res;
      if (segment === 'friends') {
        res = await getFriendsTop(lbId, userId, limit);
        setEntries(res.data.entries || []);
        setTotalUsers(res.data.total_friends || 0);
      } else {
        const params = { segment, page, limit };
        if (segment === 'regional' && region) params.region = region;
        res = await getTop(lbId, params);
        setEntries(res.data.entries || []);
        setTotalUsers(res.data.total_users || 0);
      }
    } catch (err) {
      console.error('Failed to fetch leaderboard:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (lbId) fetchData();
  }, [lbId, segment, page, region]);

  // Handle WebSocket messages — update table in place
  useEffect(() => {
    if (!wsMessage) return;

    if (wsMessage.type === 'leaderboard_update') {
      // Refresh the full table to get updated data
      fetchData();
    }

    if (wsMessage.type === 'rank_change') {
      const uid = wsMessage.user_id;
      const direction = (wsMessage.previous_rank && wsMessage.new_rank < wsMessage.previous_rank)
        ? 'rank-up' : 'rank-down';
      setFlashRows((prev) => ({ ...prev, [uid]: direction }));
      setTimeout(() => {
        setFlashRows((prev) => {
          const copy = { ...prev };
          delete copy[uid];
          return copy;
        });
      }, 1500);
      // Refresh data to reflect new positions
      fetchData();
    }

    if (wsMessage.type === 'displaced') {
      fetchData();
    }
  }, [wsMessage]);

  const totalPages = Math.ceil(totalUsers / limit) || 1;

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between">
        <span className="text-sm font-bold uppercase tracking-[0.5px] text-text-secondary">🏆 Leaderboard</span>
        <span className="text-[12px] text-muted">
          {totalUsers} players
        </span>
      </div>

      {/* Segment Tabs */}
      <div className="pt-3 px-5">
        <div className="flex gap-1 p-1 bg-primary rounded-lg overflow-x-auto">
          {SEGMENTS.map((seg) => (
            <button
              key={seg.key}
              className={`px-4 py-2 border-none rounded-md bg-transparent text-muted text-[13px] font-semibold whitespace-nowrap transition-all duration-200 hover:text-text-secondary hover:bg-card-hover ${segment === seg.key ? 'bg-accent text-white shadow-[0_2px_8px_var(--tw-colors-accent-glow)]' : ''}`}
              onClick={() => { setSegment(seg.key); setPage(1); }}
            >
              {seg.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="pb-3">
        {loading ? (
          <div className="flex items-center justify-center p-10 text-muted text-sm gap-2.5">
            <div className="w-[18px] h-[18px] border-2 border-border border-t-accent rounded-full animate-spin" />
            Loading...
          </div>
        ) : entries.length === 0 ? (
          <div className="flex items-center justify-center p-10 text-muted text-sm gap-2.5">
            No entries yet. Submit some scores!
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                <tr>
                  <th className="w-[60px] px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-[0.8px] text-muted border-b border-border">Rank</th>
                  <th className="px-4 py-2.5 text-left text-[11px] font-bold uppercase tracking-[0.8px] text-muted border-b border-border">Player</th>
                  <th className="px-4 py-2.5 text-right text-[11px] font-bold uppercase tracking-[0.8px] text-muted border-b border-border">Score</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr
                    key={entry.user_id}
                    className={`hover:bg-card-hover transition-colors ${flashRows[entry.user_id] === 'rank-up' ? 'animate-flashGreen' : flashRows[entry.user_id] === 'rank-down' ? 'animate-flashRed' : ''}`}
                    style={entry.user_id === userId ? { background: 'rgba(99,102,241,0.06)' } : {}}
                  >
                    <td className="px-4 py-3 text-sm border-b border-[#2a335480]"><RankBadge rank={entry.rank} /></td>
                    <td className="px-4 py-3 text-sm border-b border-[#2a335480] font-semibold">
                      {entry.username || entry.user_id.slice(0, 8)}
                      {entry.user_id === userId && (
                        <span className="ml-2 text-[11px] text-accent font-medium">YOU</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm border-b border-[#2a335480] text-right font-semibold tabular-nums text-accent-hover">
                      {Number(entry.score).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && segment !== 'friends' && (
              <div className="flex justify-center gap-2 px-5 py-3 border-t border-border">
                <button
                  className="px-4 py-2 border-none rounded-md bg-transparent text-muted text-[13px] font-semibold whitespace-nowrap transition-all duration-200 hover:text-text-secondary hover:bg-card-hover disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                >
                  ← Prev
                </button>
                <span className="px-3 py-2 text-[13px] text-muted">
                  Page {page} of {totalPages}
                </span>
                <button
                  className="px-4 py-2 border-none rounded-md bg-transparent text-muted text-[13px] font-semibold whitespace-nowrap transition-all duration-200 hover:text-text-secondary hover:bg-card-hover disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                >
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
