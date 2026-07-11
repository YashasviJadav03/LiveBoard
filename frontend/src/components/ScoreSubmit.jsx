import { useState } from 'react';
import { submitScore } from '../api';

export default function ScoreSubmit({ lbId, users, onScoreSubmitted }) {
  const [selectedUser, setSelectedUser] = useState('');
  const [delta, setDelta] = useState('');
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedUser || !delta) return;

    setSubmitting(true);
    setResult(null);

    try {
      const res = await submitScore(lbId, selectedUser, parseInt(delta, 10));
      const data = res.data;

      let message = `Score updated! New rank: #${data.new_rank} (${data.new_score} pts)`;
      if (data.rank_change && data.rank_change > 0) {
        message = `🎉 Moved up ${data.rank_change} position${data.rank_change > 1 ? 's' : ''}! Now #${data.new_rank}`;
      } else if (data.rank_change && data.rank_change < 0) {
        message = `Dropped ${Math.abs(data.rank_change)} position${Math.abs(data.rank_change) > 1 ? 's' : ''}. Now #${data.new_rank}`;
      }

      setResult({ type: 'success', message });
      setDelta('');
      onScoreSubmitted?.(data);
    } catch (err) {
      setResult({
        type: 'error',
        message: err.response?.data?.detail || 'Failed to submit score',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-border">
        <span className="text-sm font-bold uppercase tracking-[0.5px] text-text-secondary">⚡ Submit Score</span>
      </div>
      <div className="px-5 py-4">
        <form onSubmit={handleSubmit}>
          <div className="mb-3.5">
            <label className="block text-xs font-semibold text-muted mb-1.5 uppercase tracking-[0.5px]">Player</label>
            <select
              className="w-full px-3.5 py-2.5 bg-primary border border-border rounded-lg text-text-primary text-sm font-sans transition-colors outline-none focus:border-accent focus:ring-[3px] focus:ring-accent-glow"
              value={selectedUser}
              onChange={(e) => setSelectedUser(e.target.value)}
            >
              <option value="">Select a player...</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.username}{u.region ? ` (${u.region})` : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="mb-3.5">
            <label className="block text-xs font-semibold text-muted mb-1.5 uppercase tracking-[0.5px]">Score Delta</label>
            <input
              type="number"
              className="w-full px-3.5 py-2.5 bg-primary border border-border rounded-lg text-text-primary text-sm font-sans transition-colors outline-none focus:border-accent focus:ring-[3px] focus:ring-accent-glow"
              placeholder="e.g. 100"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
              step="any"
            />
          </div>

          <button
            type="submit"
            className="w-full p-3 border-none rounded-lg bg-gradient-to-br from-accent to-[#7c3aed] text-white text-sm font-bold font-sans cursor-pointer transition-all duration-200 mt-1 hover:-translate-y-[1px] hover:shadow-[0_4px_16px_var(--tw-colors-accent-glow)] active:translate-y-0 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
            disabled={submitting || !selectedUser || !delta}
          >
            {submitting ? 'Submitting...' : 'Submit Score'}
          </button>
        </form>

        {result && (
          <div className={`mt-3 p-3 text-[13px] font-medium rounded-lg animate-[slideIn_0.3s_ease] ${result.type === 'success' ? 'bg-green-glow border border-[rgba(16,185,129,0.3)] text-green' : 'bg-red-glow border border-[rgba(239,68,68,0.3)] text-red'}`}>
            {result.message}
          </div>
        )}
      </div>
    </div>
  );
}
