import { useState, useEffect, useCallback } from 'react';
import './index.css';
import LeaderboardTable from './components/LeaderboardTable';
import ScoreSubmit from './components/ScoreSubmit';
import MyRank from './components/MyRank';
import ScoreHistory from './components/ScoreHistory';
import { ToastContainer, useToasts } from './components/Toast';
import CreatePlayerModal from './components/CreatePlayerModal';
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
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Check backend health
  useEffect(() => {
    getHealth()
      .then(() => setBackendOk(true))
      .catch(() => setBackendOk(false));
  }, []);

  // Fetch users + ensure demo leaderboard exists
  useEffect(() => {
    const fetchUsers = async () => {
      try {
        const res = await fetch(`${API_BASE}/users`);
        if (res.ok) {
          const fetched = await res.json();
          setUsers(fetched);
          if (fetched.length > 0 && !currentUserId) {
            setCurrentUserId(fetched[0].id);
          }
        }
      } catch (err) {
        console.error('Failed to fetch users', err);
      }
    };

    const init = async () => {
      try {
        // Ensure leaderboard exists
        await fetch(`${API_BASE}/leaderboards`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: DEMO_LB_ID, name: 'Live Coding Contest' }),
        }).catch(() => {});
        
        await fetchUsers();
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
      // Too noisy with the bot running continuously:
      // addToast('Leaderboard updated!', 'update');
    }
  }, [addToast]);

  const { connected } = useWebSocket(lbId, currentUserId, handleWsMessage);

  const handleScoreSubmitted = () => {
    // WS will handle the live updates
  };

  const handlePlayerCreated = (newUser) => {
    setUsers((prev) => [newUser, ...prev]);
    setCurrentUserId(newUser.id);
    setShowCreateModal(false);
  };

  if (backendOk === false) {
    return (
      <div className="max-w-[1400px] mx-auto px-4 sm:px-8 py-4 sm:py-6">
        <div className="text-center py-20 px-5 text-muted text-base">
          <div className="text-5xl mb-4">⚠️</div>
          <h2 className="text-text-primary mb-2 text-2xl font-bold">Backend Not Running</h2>
          <p>Make sure Docker is running and execute:</p>
          <code className="inline-block mt-3 py-2.5 px-5 bg-card rounded-lg text-accent-hover font-mono">
            docker compose up --build
          </code>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-4 sm:px-8 py-4 sm:py-6">
      <ToastContainer toasts={toasts} />

      {/* Header */}
      <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 sm:gap-0 mb-6 sm:mb-8 pb-6 border-b border-border">
        <div>
          <h1 className="text-[24px] sm:text-[28px] font-extrabold tracking-tight bg-gradient-to-br from-accent to-[#a78bfa] bg-clip-text text-transparent">LiveBoard</h1>
          <p className="text-[12px] sm:text-[13px] text-muted mt-1">Real-time leaderboard dashboard</p>
        </div>
        <div className="flex items-center gap-3 sm:gap-4 w-full sm:w-auto">
          {/* User selector */}
          <select
            className="flex-1 sm:w-[200px] sm:flex-none px-3.5 py-2.5 bg-primary border border-border rounded-lg text-text-primary text-sm font-sans transition-colors outline-none focus:border-accent focus:ring-[3px] focus:ring-accent-glow"
            value={currentUserId}
            onChange={(e) => setCurrentUserId(e.target.value)}
          >
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                👤 {u.username}
              </option>
            ))}
          </select>

          <button
            onClick={() => setShowCreateModal(true)}
            className="px-3.5 py-2.5 bg-accent hover:bg-accent-hover text-white rounded-lg text-sm font-semibold shadow-lg shadow-accent/20 transition-all"
          >
            + New Player
          </button>

          <div className={`flex items-center gap-2 px-[14px] py-1.5 rounded-[20px] text-xs font-semibold bg-card border border-border ${connected ? 'border-green text-green' : 'border-red text-red'}`}>
            <span className={`w-2 h-2 rounded-full bg-current ${connected ? 'animate-pulse' : ''}`} />
            {connected ? 'Live' : 'Offline'}
          </div>
        </div>
      </header>

      {showCreateModal && (
        <CreatePlayerModal
          onClose={() => setShowCreateModal(false)}
          onCreated={handlePlayerCreated}
        />
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-6">
        {/* Left: Leaderboard Table */}
        <LeaderboardTable
          lbId={lbId}
          userId={currentUserId}
          wsMessage={wsMessage}
        />

        {/* Right: Sidebar */}
        <div className="flex flex-col gap-5">
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
