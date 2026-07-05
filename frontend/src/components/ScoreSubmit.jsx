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
      const res = await submitScore(lbId, selectedUser, parseFloat(delta));
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
    <div className="card">
      <div className="card-header">
        <span className="card-title">⚡ Submit Score</span>
      </div>
      <div className="card-body">
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Player</label>
            <select
              className="form-select"
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

          <div className="form-group">
            <label className="form-label">Score Delta</label>
            <input
              type="number"
              className="form-input"
              placeholder="e.g. 100"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
              step="any"
            />
          </div>

          <button
            type="submit"
            className="btn-submit"
            disabled={submitting || !selectedUser || !delta}
          >
            {submitting ? 'Submitting...' : 'Submit Score'}
          </button>
        </form>

        {result && (
          <div className={`submit-result ${result.type}`}>
            {result.message}
          </div>
        )}
      </div>
    </div>
  );
}
