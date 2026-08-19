**Startup Guide**

This guide explains how to start the NovaCart support assistant locally from scratch, where to place `.env` files, what to include in them, and the steps to run both backend and frontend when your Git repo contains only the `frontend` and `backend` folders.

**Prerequisites:**
- Install Python 3.10+ and Node 18+ (or the versions used in your environment).
- Git clone the repository so you have the `ecommerce-support-bot` folder locally.

**Repository layout (relevant parts):**
- `ecommerce-support-bot/backend` — FastAPI backend (Python)
- `ecommerce-support-bot/frontend` — Vite + React frontend

**Where to put `.env` files**
- Backend: place the environment file at `ecommerce-support-bot/backend/.env` (the backend loads `BASE_DIR / ".env"`).
- Frontend: place the Vite env file at `ecommerce-support-bot/frontend/.env` (or `.env.local`).
- DO NOT commit your `.env` files. Instead commit `.env.example` files and keep `.env` listed in `.gitignore` (this repo already ignores them).

**What to put in the env files**

Backend example (`ecommerce-support-bot/backend/.env`):

GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=openai/gpt-oss-120b
# Optional (only if you override):
# GROQ_BASE_URL=https://api.groq.com/openai/v1
# DATABASE_URL=sqlite:///./app.db

Notes:
- `GROQ_API_KEY` is required for the LLM client used in `app/llm/client.py`.
- `GROQ_MODEL` and `GROQ_BASE_URL` have reasonable defaults and can be left out unless you need to override them.
- `DATABASE_URL` can be left out to use the default SQLite file `backend/app.db`.

Frontend example (`ecommerce-support-bot/frontend/.env`):

VITE_API_BASE_URL=http://localhost:8000

Notes:
- `VITE_API_BASE_URL` tells the frontend where the backend runs. During development this typically points to `http://localhost:8000`.

**Setup and run — Backend (Windows PowerShell)**

1. Open a terminal in `ecommerce-support-bot/backend`.
2. Create and activate a virtual environment, then install requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # PowerShell
pip install --upgrade pip
pip install -r requirements.txt
```

3. Create your `backend/.env` by copying `backend/.env.example` and filling values.

4. (Optional) If you plan to use the RAG index, place your PDF knowledge-base files in `backend/data/kb/` and run the index builder:

```powershell
python scripts\build_index.py
```

5. Run the backend server (development):

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The health endpoint will be available at `http://localhost:8000/health`.

**Setup and run — Frontend**

1. Open a terminal in `ecommerce-support-bot/frontend`.
2. Install dependencies and start the dev server:

```bash
npm install
npm run dev
```

3. Ensure your `frontend/.env` (or `.env.local`) contains `VITE_API_BASE_URL` pointing to the backend (default `http://localhost:8000`).

The dev server will typically be served at `http://localhost:5173` (Vite default).

**Notes about Git and deployment**
- If you are pushing only `frontend` and `backend` directories to Git:
  - Commit `backend/.env.example` and `frontend/.env.example` (templates) but never commit `.env`.
  - On each target machine (developer laptop, server, or CI), create the real `backend/.env` and `frontend/.env` via environment-specific secrets or secure config systems.
- This repo already has `.gitignore` entries to prevent committing `.env` files and generated data like FAISS indexes.


