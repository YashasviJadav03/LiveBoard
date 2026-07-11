import { useState } from 'react';

export default function CreatePlayerModal({ onClose, onCreated }) {
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [region, setRegion] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim()) return;

    setLoading(true);
    setError('');
    
    try {
      const res = await fetch(`${API_BASE}/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: username.trim(),
          display_name: displayName.trim() || undefined,
          region: region.trim() || undefined,
        }),
      });
      
      if (res.ok || res.status === 201) {
        const user = await res.json();
        onCreated(user);
      } else {
        const data = await res.json();
        setError(data.detail || 'Failed to create user');
      }
    } catch (err) {
      setError('Network error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-toastIn">
      <div className="bg-card border border-border rounded-xl p-6 w-full max-w-md shadow-2xl">
        <h2 className="text-xl font-bold text-text-primary mb-4">Create New Player</h2>
        
        {error && (
          <div className="mb-4 p-3 bg-red-glow border border-red text-red rounded-lg text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="block text-xs font-bold text-muted mb-1.5 uppercase tracking-wider">Username *</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3.5 py-2 bg-primary border border-border rounded-lg text-text-primary text-sm outline-none focus:border-accent focus:ring-[3px] focus:ring-accent-glow transition-all"
              placeholder="e.g. nova_star"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-muted mb-1.5 uppercase tracking-wider">Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full px-3.5 py-2 bg-primary border border-border rounded-lg text-text-primary text-sm outline-none focus:border-accent focus:ring-[3px] focus:ring-accent-glow transition-all"
              placeholder="e.g. Nova"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-muted mb-1.5 uppercase tracking-wider">Region</label>
            <input
              type="text"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="w-full px-3.5 py-2 bg-primary border border-border rounded-lg text-text-primary text-sm outline-none focus:border-accent focus:ring-[3px] focus:ring-accent-glow transition-all"
              placeholder="e.g. US-EAST"
            />
          </div>

          <div className="flex justify-end gap-3 mt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 bg-accent hover:bg-accent-hover text-white text-sm font-semibold rounded-lg shadow-lg shadow-accent/20 transition-all disabled:opacity-50"
            >
              {loading ? 'Creating...' : 'Create Player'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
