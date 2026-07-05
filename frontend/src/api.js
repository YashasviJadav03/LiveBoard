import axios from 'axios';

const API_BASE = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// ── Leaderboard ──────────────────────────────────
export const createLeaderboard = (id, name) =>
  api.post('/leaderboards', { id, name });

export const getTop = (lbId, { segment = 'all_time', page = 1, limit = 50, region } = {}) => {
  const params = { segment, page, limit };
  if (region) params.region = region;
  return api.get(`/leaderboards/${lbId}/top`, { params });
};

export const getUserRank = (lbId, userId) =>
  api.get(`/leaderboards/${lbId}/rank/${userId}`);

export const getFriendsTop = (lbId, userId, limit = 50) =>
  api.get(`/leaderboards/${lbId}/friends/${userId}/top`, { params: { limit } });

// ── Scores ───────────────────────────────────────
export const submitScore = (lbId, userId, delta) =>
  api.post(`/leaderboards/${lbId}/scores`, { user_id: userId, delta });

// ── Score History ────────────────────────────────
export const getScoreHistory = (lbId, userId, limit = 100) =>
  api.get(`/leaderboards/${lbId}/users/${userId}/history`, { params: { limit } });

// ── Users ────────────────────────────────────────
export const getUsers = () => api.get('/users');
export const createUser = (username, displayName, region) =>
  api.post('/users', { username, display_name: displayName, region });

// ── Health ───────────────────────────────────────
export const getHealth = () => api.get('/health');

export default api;
