# Sprint 7: Production Deployment

## Goal
Deploy the frontend and backend services to scalable cloud providers for live access.

## Key Accomplishments
- **Render Backend Deployment**: Configured `render.yaml` to deploy FastAPI along with managed PostgreSQL and Redis clusters.
- **Vercel Frontend Deployment**: Configured `vercel.json` for frontend routing and deployed the Vite app to Vercel.
- **Environment Configuration**: Set up CORS policies and environment variable pipelines to securely link Render APIs to the Vercel app. Implemented automatic protocol derivation to upgrade `https://` (from `VITE_API_URL`) to `wss://` for production WebSocket connections, eliminating the need for separate environment variables.
- **Final Polish**: Finalized documentation, screenshots, and diagrams for the open-source repository.

## Deliverables
- `render.yaml`
- `frontend/vercel.json`
- Comprehensive deployment instructions in `README.md`.
