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
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-border flex items-center justify-between">
        <span className="text-sm font-bold uppercase tracking-[0.5px] text-text-secondary">📈 Score History</span>
        <span className="text-[12px] text-muted">
          {data.length} events
        </span>
      </div>

      {loading && data.length === 0 ? (
        <div className="flex items-center justify-center p-10 text-muted text-sm gap-2.5">
          <div className="w-[18px] h-[18px] border-2 border-border border-t-accent rounded-full animate-spin" />
          Loading...
        </div>
      ) : data.length === 0 ? (
        <div className="py-10 px-5 text-center text-muted text-sm">
          No score history yet.<br />Submit some scores to see the chart!
        </div>
      ) : (
        <div className="pt-4 px-2 pb-2">
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={data}>
              <defs>
                <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a3354" />
              <XAxis
                dataKey="time"
                stroke="#5a6580"
                fontSize={11}
                tickLine={false}
              />
              <YAxis
                stroke="#5a6580"
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
