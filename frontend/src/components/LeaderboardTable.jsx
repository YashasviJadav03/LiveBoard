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
  let cls = 'default';
  if (rank === 1) cls = 'gold';
  else if (rank === 2) cls = 'silver';
  else if (rank === 3) cls = 'bronze';
  return <span className={`rank-badge ${cls}`}>{rank}</span>;
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
    <div className="card">
      <div className="card-header">
        <span className="card-title">🏆 Leaderboard</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {totalUsers} players
        </span>
      </div>

      {/* Segment Tabs */}
      <div style={{ padding: '12px 20px 0' }}>
        <div className="segment-tabs">
          {SEGMENTS.map((seg) => (
            <button
              key={seg.key}
              className={`segment-tab ${segment === seg.key ? 'active' : ''}`}
              onClick={() => { setSegment(seg.key); setPage(1); }}
            >
              {seg.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div style={{ padding: '0 0 12px' }}>
        {loading ? (
          <div className="loading">
            <div className="spinner" />
            Loading...
          </div>
        ) : entries.length === 0 ? (
          <div className="loading" style={{ color: 'var(--text-muted)' }}>
            No entries yet. Submit some scores!
          </div>
        ) : (
          <>
            <table className="lb-table">
              <thead>
                <tr>
                  <th style={{ width: 60 }}>Rank</th>
                  <th>Player</th>
                  <th style={{ textAlign: 'right' }}>Score</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr
                    key={entry.user_id}
                    className={flashRows[entry.user_id] || ''}
                    style={entry.user_id === userId ? { background: 'rgba(99,102,241,0.06)' } : {}}
                  >
                    <td><RankBadge rank={entry.rank} /></td>
                    <td className="username-cell">
                      {entry.username || entry.user_id.slice(0, 8)}
                      {entry.user_id === userId && (
                        <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--accent)', fontWeight: 500 }}>YOU</span>
                      )}
                    </td>
                    <td className="score-cell" style={{ textAlign: 'right' }}>
                      {Number(entry.score).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            {totalPages > 1 && segment !== 'friends' && (
              <div style={{
                display: 'flex', justifyContent: 'center', gap: 8,
                padding: '12px 20px', borderTop: '1px solid var(--border)'
              }}>
                <button
                  className="segment-tab"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                >
                  ← Prev
                </button>
                <span style={{ padding: '8px 12px', fontSize: 13, color: 'var(--text-muted)' }}>
                  Page {page} of {totalPages}
                </span>
                <button
                  className="segment-tab"
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
