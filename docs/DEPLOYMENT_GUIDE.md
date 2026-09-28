# Enterprise Cloud Deployment Guide: Turnkey Free-Tier Stack

This guide details how to deploy the **Autonomous Talent Screening Platform** to production using 100% free-tier cloud infrastructure for live presentations, competitions, and client demonstrations.

```
                          ┌─────────────────────────────────────┐
                          │         Vercel (Free Tier)          │
                          │     Next.js 16 App Router UI        │
                          │   https://your-platform.vercel.app  │
                          └──────────────────┬──────────────────┘
                                             │ REST & SSE API
                                             ▼
                          ┌─────────────────────────────────────┐
                          │   Render / Fly.io / Railway (Free)  │
                          │       FastAPI Async Engine          │
                          │   https://your-api.onrender.com     │
                          └───────┬─────────────────────┬───────┘
                                  │                     │
                    SQLAlchemy    │                     │ Vector Index
                    AsyncPG       │                     │ Cosine Similarity
                                  ▼                     ▼
             ┌──────────────────────────────┐    ┌────────────────────────┐
             │    Neon Serverless Postgres  │    │  ChromaDB Cloud / Vol  │
             │   (Free 0.5 GB Serverless)   │    │  (Persistent Storage)  │
             └──────────────────────────────┘    └────────────────────────┘
```

---

## 1. Database Tier: Neon Serverless PostgreSQL (Free)

1. Sign up at [neon.tech](https://neon.tech) (Free tier includes 0.5 GB storage, serverless autoscaling to zero).
2. Create a new project: `recruitment-screening-prod`.
3. Copy your async connection string from the dashboard:
   ```text
   postgresql+asyncpg://[user]:[password]@[endpoint].neon.tech/[dbname]?sslmode=require
   ```
4. Run Alembic migrations against your Neon database from your local machine:
   ```bash
   DATABASE_URL="postgresql+asyncpg://[user]:[password]@[endpoint].neon.tech/[dbname]?sslmode=require" alembic upgrade head
   ```
   *All 6 enterprise relational tables (`candidates`, `job_requisitions`, `job_requirements`, `match_evaluations`, `interview_plans`, `batch_jobs`, `audit_logs`) will be initialized instantly.*

---

## 2. Backend Tier: Render / Fly.io / Koyeb (Free)

### Deploying on Render (Recommended)
1. Sign up at [render.com](https://render.com).
2. Click **New +** → **Web Service**.
3. Connect your GitHub repository (branch `feat/enterprise-platform` or `main`).
4. Configure service settings:
   - **Name:** `recruitment-screening-api`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
5. Configure Environment Variables in Render Dashboard:
   | Key | Value / Description |
   | :--- | :--- |
   | `DATABASE_URL` | Your Neon connection string (`postgresql+asyncpg://...`) |
   | `LLM_PROVIDER` | `groq` |
   | `GROQ_API_KEY` | Your Groq Cloud API key (Free at console.groq.com) |
   | `OPENROUTER_API_KEY` | *(Optional failover tier 2)* |
   | `ENVIRONMENT` | `production` |
   | `DEBUG` | `false` |
6. Click **Deploy Web Service**. Render will build and provide your public URL:
   `https://recruitment-screening-api.onrender.com`
7. Test the health endpoint: `https://recruitment-screening-api.onrender.com/health` (should return 200 OK with active provider info).

---

## 3. Frontend Tier: Vercel (Free)

1. Sign up at [vercel.com](https://vercel.com).
2. Click **Add New...** → **Project**.
3. Import your GitHub repository.
4. In the Project Setup:
   - **Root Directory:** Edit to select `frontend-next`
   - **Framework Preset:** `Next.js`
   - **Build Command:** `next build`
   - **Output Directory:** `.next`
5. Add Environment Variable:
   | Key | Value |
   | :--- | :--- |
   | `NEXT_PUBLIC_API_URL` | `https://recruitment-screening-api.onrender.com` |
6. Click **Deploy**. Vercel compiles Turbopack, runs strict TypeScript typechecks, and provides an instant global edge CDN URL:
   `https://recruitment-screening-platform.vercel.app`

---

## 4. Local Turnkey Demonstration (Zero-Cloud Mode)

If running the live presentation on your local laptop (e.g. without relying on conference Wi-Fi):

1. **One-Click Execution:**
   Double-click `start_enterprise.bat` or run:
   ```bash
   python start_enterprise.py
   ```
2. The orchestrator boots:
   - FastAPI Backend on `http://localhost:8000` (backed by local `sqlite+aiosqlite` and ChromaDB).
   - Next.js 16 Dark UI on `http://localhost:3000`.
   - Automated local model fallback via Ollama if cloud Wi-Fi disconnects!
3. Open `http://localhost:3000` in Google Chrome or Microsoft Edge and press `F11` for full-screen executive demo.
