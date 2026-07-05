import { useEffect, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Area, AreaChart,
} from 'recharts';
import { getScoreHistory } from '../api';

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 8,
      padding: '10px 14px',
      fontSize: 13,
    }}>
      <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      <div style={{ color: 'var(--accent-hover)', fontWeight: 600 }}>
        Score: {Number(payload[0].value).toLocaleString()}
      </div>
      {payload[0]?.payload?.score_delta != null && (
        <div style={{ color: 'var(--green)', fontSize: 12, marginTop: 2 }}>
          +{payload[0].payload.score_delta}
        </div>
      )}
    </div>
  );
}

export default function ScoreHistory({ lbId, userId, wsMessage }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchHistory = async () => {
    if (!lbId || !userId) return;
    setLoading(true);
    try {
      const res = await getScoreHistory(lbId, userId);
      const entries = (res.data.entries || []).map((e) => ({
        ...e,
        time: new Date(e.recorded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        total_score: Number(e.total_score),
        score_delta: Number(e.score_delta),
      }));
      setData(entries);
    } catch (err) {
      console.error('Failed to fetch history:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [lbId, userId]);

  // Refresh on new score submissions
  useEffect(() => {
    if (wsMessage?.type === 'rank_change' || wsMessage?.type === 'leaderboard_update') {
      fetchHistory();
    }
  }, [wsMessage]);

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">📈 Score History</span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {data.length} events
        </span>
      </div>

      {loading && data.length === 0 ? (
        <div className="loading"><div className="spinner" />Loading...</div>
      ) : data.length === 0 ? (
        <div className="chart-empty">
          No score history yet.<br />Submit some scores to see the chart!
        </div>
      ) : (
        <div className="chart-container">
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={data}>
              <defs>
                <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="time"
                stroke="var(--text-muted)"
                fontSize={11}
                tickLine={false}
              />
              <YAxis
                stroke="var(--text-muted)"
                fontSize={11}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="total_score"
                stroke="#6366f1"
                strokeWidth={2}
                fill="url(#scoreGradient)"
                dot={{ fill: '#6366f1', r: 3 }}
                activeDot={{ r: 5, fill: '#818cf8' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
