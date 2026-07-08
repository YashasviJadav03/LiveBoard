import { useState, useEffect, useCallback } from 'react';
import './index.css';
import LeaderboardTable from './components/LeaderboardTable';
import ScoreSubmit from './components/ScoreSubmit';
import MyRank from './components/MyRank';
import ScoreHistory from './components/ScoreHistory';
import { ToastContainer, useToasts } from './components/Toast';
import useWebSocket from './hooks/useWebSocket';
import { getHealth } from './api';

// ── Demo config ──────────────────────────────────
// These will be replaced by UI controls or URL params in production
const DEMO_LB_ID = 'coding_contest';
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function App() {
  const [lbId] = useState(DEMO_LB_ID);
  const [currentUserId, setCurrentUserId] = useState('');
  const [users, setUsers] = useState([]);
  const [wsMessage, setWsMessage] = useState(null);
  const [toasts, addToast] = useToasts();
  const [backendOk, setBackendOk] = useState(null);

  // Check backend health
  useEffect(() => {
    getHealth()
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false));
  }, []);

  // Fetch users + ensure demo leaderboard exists
  useEffect(() => {
    const init = async () => {
      try {
        // Create demo leaderboard (ignore 409 if exists)
        await fetch(`${API_BASE}/leaderboards`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: DEMO_LB_ID, name: 'Demo Leaderboard' }),
        });

        // Create some demo users if none exist
        const usersToCreate = [
          { username: 'alex_storm', display_name: 'Alex Storm', region: 'US-EAST' },
          { username: 'maya_fire', display_name: 'Maya Fire', region: 'EU-WEST' },
          { username: 'kai_zen', display_name: 'Kai Zen', region: 'ASIA' },
          { username: 'nova_star', display_name: 'Nova Star', region: 'US-WEST' },
          { username: 'zara_light', display_name: 'Zara Light', region: 'EU-WEST' },
        ];

        for (const u of usersToCreate) {
          await fetch(`${API_BASE}/users`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(u),
          }).catch(() => {});
        }

        // Fetch all users (we need a list endpoint)
        // Since we don't have GET /users, we'll create and track them
        const fetched = [];
        for (const u of usersToCreate) {
          try {
            const res = await fetch(`${API_BASE}/users`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(u),
            });
            if (res.status === 201) {
              fetched.push(await res.json());
            }
          } catch {}
        }

        // If users already existed, find them by trying to get their scores
        // Workaround: query the leaderboard top to find existing users
        if (fetched.length === 0) {
          try {
            const topRes = await fetch(`${API_BASE}/leaderboards/${DEMO_LB_ID}/top?limit=50`);
            if (topRes.ok) {
              const topData = await topRes.json();
              for (const entry of topData.entries || []) {
                fetched.push({
                  id: entry.user_id,
                  username: entry.username || entry.user_id.slice(0, 8),
                });
              }
            }
          } catch {}
        }

        // Fallback: re-create users and get them
        if (fetched.length === 0) {
          // Users exist but we can't list them. Use the created users from above.
          for (const u of usersToCreate) {
            try {
              const searchRes = await fetch(`${API_BASE}/users`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(u),
              });
              const body = await searchRes.json();
              if (searchRes.status === 201) fetched.push(body);
            } catch {}
          }
        }

        setUsers(fetched);
        if (fetched.length > 0 && !currentUserId) {
          setCurrentUserId(fetched[0].id);
        }
      } catch (err) {
        console.error('Init error:', err);
      }
    };

    init();
  }, []);

  // WebSocket message handler
  const handleWsMessage = useCallback((msg) => {
    setWsMessage({ ...msg, _ts: Date.now() }); // add timestamp to force re-renders

    if (msg.type === 'rank_change' && msg.message) {
      addToast(msg.message, 'rank-change');
    } else if (msg.type === 'displaced') {
      addToast(
        `You were displaced from #${msg.previous_rank} to #${msg.new_rank}${msg.displaced_by ? ` by ${msg.displaced_by}` : ''}`,
        'displaced'
      );
    } else if (msg.type === 'leaderboard_update') {
      addToast('Leaderboard updated!', 'update');
    }
  }, [addToast]);

  const { connected } = useWebSocket(lbId, currentUserId, handleWsMessage);

  const handleScoreSubmitted = () => {
    // WS will handle the live updates
  };

  if (backendOk === false) {
    return (
      <div className="app-container">
        <div style={{
          textAlign: 'center', padding: '80px 20px',
          color: 'var(--text-muted)', fontSize: 16
        }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
          <h2 style={{ color: 'var(--text-primary)', marginBottom: 8 }}>Backend Not Running</h2>
          <p>Make sure Docker is running and execute:</p>
          <code style={{
            display: 'inline-block', marginTop: 12, padding: '10px 20px',
            background: 'var(--bg-card)', borderRadius: 8, color: 'var(--accent-hover)'
          }}>
            docker compose up --build
          </code>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      <ToastContainer toasts={toasts} />

      {/* Header */}
      <header className="app-header">
        <div>
          <h1 className="app-title">LiveBoard</h1>
          <p className="app-subtitle">Real-time leaderboard dashboard</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          {/* User selector */}
          <select
            className="form-select"
            style={{ width: 200 }}
            value={currentUserId}
            onChange={(e) => setCurrentUserId(e.target.value)}
          >
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                👤 {u.username}
              </option>
            ))}
          </select>

          <div className={`connection-badge ${connected ? 'connected' : 'disconnected'}`}>
            <span className="connection-dot" />
            {connected ? 'Live' : 'Offline'}
          </div>
        </div>
      </header>

      {/* Main Grid */}
      <div className="main-grid">
        {/* Left: Leaderboard Table */}
        <LeaderboardTable
          lbId={lbId}
          userId={currentUserId}
          wsMessage={wsMessage}
        />

        {/* Right: Sidebar */}
        <div className="sidebar">
          <ScoreSubmit
            lbId={lbId}
            users={users}
            onScoreSubmitted={handleScoreSubmitted}
          />
          <MyRank
            lbId={lbId}
            userId={currentUserId}
            wsMessage={wsMessage}
          />
          <ScoreHistory
            lbId={lbId}
            userId={currentUserId}
            wsMessage={wsMessage}
          />
        </div>
      </div>
    </div>
  );
}
