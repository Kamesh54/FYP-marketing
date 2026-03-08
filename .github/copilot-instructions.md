# Copilot instructions for this repository

Purpose: quick, actionable guidance so an AI coding assistant becomes productive
in this multi-agent content-marketing platform.

1) Big picture (read these first)
- Orchestrator: `orchestrator.py` (port 8004) — JWT auth, intent routing, workflow orchestration.
- Agent services: `webcrawler.py` (8000), `keywordExtraction.py` (8001), `CompetitorGapAnalyzerAgent.py` (8002),
  `content_agent.py` (8003), `seo_agent.py` (5000), `reddit_agent.py` (8010). Each agent is a small FastAPI app.
- Data: SQLite via `database.py`, local file storage (`generated_images/`, `previews/`, `tmp1/`), and an in-repo cache.

2) How services communicate (important patterns)
- Job-based async pattern: POST to a `/...` endpoint returns `{job_id, status}`; poll `GET /status/{job_id}` then
  `GET /download/{job_id}` for results (example: `POST /crawl` -> `GET /download/{job_id}` in `webcrawler.py`).
- Ports are fixed per-agent; code assumes those ports for orchestration. Avoid changing ports without updating `start.bat` and docs.

3) Local run & useful commands (concrete)
- Windows: run `start.bat` at repo root — it kills processes on 8000–8004 and launches each agent in a new window.
- Run services individually (examples):
  - `python webcrawler.py`
  - `python keywordExtraction.py`
  - `python content_agent.py`
  - `python orchestrator.py`
- Initialize DB: `python -c "import database; database.initialize_database()"`
- Frontend: see `frontend/` (Next.js). Install with `pnpm install` or `npm install` and run per Next.js docs.

4) Environment & secrets (must be present for realistic runs)
- Required `.env` keys referenced in README/docs: `GROQ_API_KEY`, `SERPAPI_API_KEY`, `JWT_SECRET`.
- Optional but commonly used: `RUNWAY_API_KEY`, `TWITTER_*`, `INSTAGRAM_*`, `AWS_*`.

5) Project-specific conventions to follow
- Every agent exposes a root health-check `GET /` returning port and version.
- Jobs follow `job_id` naming conventions (e.g. `crawl_{domain}_{timestamp}_{uuid}` in `webcrawler.py`).
- Use the job status lifecycle: `queued` -> `running` -> `completed` | `failed`.
- LLM usage is centralized via Groq client calls — prompts constructed in agent code and docs (see `docs/CONTENT_AGENT_README.md`).

6) Key files to inspect when changing behavior
- Orchestration and routing: `orchestrator.py`, `intelligent_router.py`, `mabo_framework.py`, `mabo_agent.py`.
- Agents: `webcrawler.py`, `keywordExtraction.py`, `CompetitorGapAnalyzerAgent.py`, `content_agent.py`, `seo_agent.py`.
- Persistence and jobs: `database.py`, `scheduler.py`, `metrics_collector.py`.
- Prompt and LLM settings: check agent README files in `docs/` and direct Groq calls in each agent file.

7) Code style & tests
- Repo follows PEP8 and uses type hints; prefer small, focused changes consistent with existing style.
- There is no centralized test suite in the top-level files; validate changes by running the specific agent locally and exercising its endpoints.

8) Examples for common tasks (copy-paste friendly)
- Start a content generation flow (local):
  1. Ensure `.env` has `GROQ_API_KEY` and `JWT_SECRET`.
  2. `python orchestrator.py` (or run `start.bat`).
  3. POST to `http://localhost:8004/chat` or call `content_agent.py` endpoints directly: `POST http://localhost:8003/generate-blog`.

9) Where to find more details
- Agent-specific implementation + prompt templates: `docs/CONTENT_AGENT_README.md`, `docs/KEYWORD_EXTRACTOR_README.md`,
  `docs/WEBCRAWLER_README.md`, `docs/AGENT_ARCHITECTURE.md`.
- High-level README: `README.md` (top-level) — contains setup, env keys, and port mappings.

If any section is unclear or you'd like me to include more examples (for prompts, unit-test guidance, or a smaller dev-friendly `docker-compose`), tell me which area to expand.
