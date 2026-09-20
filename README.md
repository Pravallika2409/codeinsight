# CodeInsight AI — AI-Powered Code Review & Bug Detection Platform

> **Status: Phase 6 of 6 — complete.** A React + Monaco frontend talks to a
> FastAPI backend that runs genuine static analysis across four languages —
> C++ (`cppcheck`), Python (`pyflakes` + `ast`), JavaScript (`ESLint`), and
> Java (`javac` + `javalang`) — and returns an explainable quality score.
> User accounts (JWT auth), projects, and persisted analysis history run on
> real PostgreSQL via SQLAlchemy + Alembic. An opt-in AI explanation layer
> (Anthropic's API, structured/validated JSON output) sits on top of the
> deterministic analysis without replacing it. Redis backs response caching
> and rate limiting, Celery provides a genuine background-job path
> (`POST /api/analyze/async` + `GET /api/tasks/{id}`), secure response
> headers are in place, and the whole stack has a Docker Compose setup.
> GitHub repository analysis (`POST /api/github/analyze`) and per-project
> analytics (`GET /api/projects/{id}/analytics`) round out the six planned
> phases. "Complete" describes the planned phases, not a claim that this is
> a finished, production-hardened product — see
> [Security considerations](#security-considerations) for what that would
> still take.

## Table of contents
- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Project structure](#project-structure)
- [Installation](#installation)
- [Environment variables](#environment-variables)
- [Running locally](#running-locally)
- [Running with Docker](#running-with-docker)
- [API documentation](#api-documentation)
- [Testing](#testing)
- [Code quality score](#code-quality-score)
- [Security considerations](#security-considerations)
- [Roadmap](#roadmap)
- [Key design decisions](#key-design-decisions)

## Overview

Most "AI code review" demos are a text box that pipes your code straight to
an LLM and prints whatever comes back. CodeInsight AI is built the other way
around: **deterministic static analysis is the source of truth**, and AI is
an opt-in explanation/reasoning layer added on top of it — never a
substitute for it. A finding's `source` field always says whether it came
from `static-analysis`, `compiler`, `complexity-analysis`, or `ai`, and
AI-sourced findings are never presented as guaranteed bugs (they're even
weighted at half severity in the quality score for exactly this reason —
see [Code quality score](#code-quality-score)).

## Features

- Monaco-based code editor with language selection: **C++, Python,
  JavaScript, Java**.
- `POST /api/analyze` — real static analysis per language:
  - **C++**: shells out to `cppcheck` (array bounds, null pointer dereferences,
    uninitialized variables, double free, memory leaks, style/performance
    warnings)
  - **Python**: `pyflakes` (undefined names, unused imports/variables, syntax
    errors) + AST-based checks (mutable default arguments, bare `except:`,
    `eval`/`exec` usage)
  - **JavaScript**: a real, fixed **ESLint** installation
    (`backend/tools/js-lint/`) — unused variables, `==` vs `===`, dangerous
    `eval`/`Function`/`javascript:` usage, async-Promise-executor bugs,
    unreachable code, syntax errors
  - **Java**: the real **`javac`** compiler (`-Xlint:all`) for genuine
    compile errors/warnings, plus **`javalang`** AST-based checks for empty
    catch blocks, overly broad `catch (Exception e)`, resources never closed
    or wrapped in try-with-resources, best-effort unused local variables, and
    hardcoded-credential / weak-hash-algorithm detection
  - Every analyzer degrades to an explicit "analyzer unavailable" INFO
    finding — never a fabricated result — if its underlying tool
    (`cppcheck`, ESLint, or `javac`) isn't installed.
- Complexity estimator that labels every result `estimated` — it detects
  loop nesting depth and a few recognizable patterns (binary search, sorting
  calls); it does **not** claim to prove exact Big-O.
- An explainable 0–100 quality score with a visible penalty breakdown
  (bugs / security / complexity / maintainability), not an arbitrary number.
- Severity levels (CRITICAL/HIGH/MEDIUM/LOW/INFO) with per-finding file,
  line, column, explanation, and suggested fix where available.
- **Results dashboard**: severity distribution bar, per-category filter
  pills (bug/security/code smell/etc.), and severity-sorted finding cards.
- **Accounts & projects (Phase 3)**: JWT-based register/login, projects
  scoped strictly to their owner (a wrong-owner project id always returns
  404, never 403 — never confirms the id exists).
- **Persisted analysis history (Phase 3)**: `POST /api/analyze` optionally
  saves a run under a project when the caller is authenticated as its
  owner and supplies `project_id`. Anonymous, unsaved analysis (the
  Phase 1/2 behavior) still works exactly as before with zero auth
  required — persistence is opt-in, not a breaking change.
- **AI review layer (Phase 4, opt-in)**: set `"include_ai_review": true`
  on the request to also get a plain-language summary, an overall
  assessment, additional issues the deterministic analyzers may have
  missed (merged into the same `findings` list with `source: "ai"`),
  refactoring recommendations, and an optional improved-code suggestion —
  all validated against a strict Pydantic schema, never trusted as free
  text. Off by default (a real API call costs money and latency); when no
  `ANTHROPIC_API_KEY` is configured, or the call fails for any reason, the
  request still succeeds and simply gets one INFO-level
  "ai-review-unavailable" finding instead.
- **Redis-backed response caching (Phase 5)**: an identical resubmission
  (same code, language, filename, and AI-review flag) is served from cache
  instead of re-running `cppcheck`/`javac`/ESLint (and the AI call, if
  requested) a second time. A Redis outage fails open to a fresh
  computation — never a failed request.
- **Redis-backed rate limiting (Phase 5)**: `POST /api/analyze` and
  `POST /api/auth/login` are rate-limited per client IP (configurable,
  disableable), implemented as a small transparent fixed-window counter
  rather than a third-party library. Also fails open on a Redis outage.
- **Background analysis via Celery (Phase 5)**: `POST /api/analyze/async`
  runs the identical pipeline as the synchronous endpoint but off the
  request thread, returning a task id immediately; `GET /api/tasks/{id}`
  polls status/result. The synchronous `POST /api/analyze` remains the
  simple default — this is an addition, not a replacement.
- **Secure response headers (Phase 5)**: `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`,
  `Strict-Transport-Security`, and a `Content-Security-Policy` (skipped on
  `/docs`/`/redoc` so Swagger UI still works) on every response.
- **GitHub repository analysis (Phase 6)**: `POST /api/github/analyze`
  takes a repo URL/slug and a project id, fetches every supported source
  file (C++/Python/JavaScript/Java, up to `GITHUB_MAX_FILES`, skipping
  anything over `GITHUB_MAX_FILE_SIZE_BYTES`) via the real GitHub API,
  runs the identical analysis pipeline on each one, persists each as its
  own analysis run under the project, and returns an aggregate
  repository-level report (files analyzed/skipped, average score, total
  findings by severity). Always asynchronous (`GET /api/github/analyze/{id}`
  to poll) since fetching and analyzing several real files can take a
  while. Requires no GitHub credentials for public repos; `GITHUB_TOKEN`
  is optional (private repos, higher rate limit).
- **Per-project analytics (Phase 6)**: `GET /api/projects/{id}/analytics`
  aggregates every persisted analysis run for a project — score trend over
  time, severity totals, the 10 most frequent rule ids, a language
  breakdown, and the 5 lowest-scoring files. Pure aggregation over
  already-persisted data; no new tables, no new write path.
- Structured error handling: oversized payloads (413), invalid languages
  (422), rate-limit violations (429), and unexpected failures (500 with no
  internal stack trace ever returned to the client).

## Architecture

```
                    React Frontend (Vite, Monaco, React Router)
                              |
                              | REST (/api/*), JWT bearer token
                              v
     Redis (Phase 5): response cache + rate-limit counters
     -- app/services/cache_service.py, app/core/rate_limit.py
     -- fails open on any Redis error (never blocks a request)
                              |
                              v
                    FastAPI Backend (app/)
                              |
                +-------------+--------------+
                |                            |
                v                            v
        Analysis Engine                AI Service (opt-in)
      (app/analyzers/*)              (app/services/ai_service.py)
     - cpp_analyzer (cppcheck)      - AnthropicAIProvider (real API,
     - python_analyzer (pyflakes)     structured/validated JSON)
     - javascript_analyzer (ESLint) - NullAIProvider (no key configured
     - java_analyzer (javac+javalang) -> instant graceful skip)
     - complexity_analyzer
                |                            |
                +-------------+--------------+
                              |
                              v
       Normalized Finding model (app/schemas/analysis.py)
       AI additional_issues merge in with source="ai"
                              |
                              v
     app/services/history_service.py (persistence bridge)
                              |
                              v
      PostgreSQL via SQLAlchemy + Alembic (app/models/*)
      users -> projects -> files -> analysis_runs -> findings
                                                    -> recommendations (AI)

     Same pipeline, off the request thread (Phase 5):
     POST /api/analyze/async -> Celery task (app/tasks/analysis_tasks.py)
                              -> Redis (broker + result backend)
                              -> a separate worker process runs the exact
                                 same run_analysis()/save_analysis_run()
     GET /api/tasks/{id}     -> polls the task's status/result

     Repository-level analysis (Phase 6, always async):
     POST /api/github/analyze -> Celery task (app/tasks/github_tasks.py)
                               -> app/services/github_service.py fetches
                                  supported files via the real GitHub API
                               -> each file runs through the identical
                                  run_analysis()/save_analysis_run() path
     GET /api/github/analyze/{id} -> polls status; aggregate report

     Analytics (Phase 6, read-only):
     GET /api/projects/{id}/analytics -> aggregates already-persisted
                                          AnalysisRun/Finding rows -- no
                                          new tables, no new write path
```

Docker Compose (`docker-compose.yml`, Phase 5) wires postgres + redis +
backend + a Celery worker + the nginx-served frontend together for a
one-command local stack.

Layers are kept separate on purpose: `api/` (routing only) → `services/`
(orchestration: `analysis_service.py`, `scoring_service.py`,
`history_service.py`, `github_service.py`) → `analyzers/` (one module per
language/concern) / `models/` (SQLAlchemy ORM) → `schemas/` (the contract
everything normalizes into). No file mixes these responsibilities.
Notably, nothing in `app/analyzers/*` or `analysis_service.py` knows the
database exists — `history_service.py` is the only place that translates
an `AnalyzeResponse` into rows and back, so the deterministic analysis
pipeline stays fully testable and reusable without a database.
`ai_service.py` is similarly isolated behind a `BaseAIProvider` interface:
`analysis_service.py` calls `get_ai_provider(settings)` and never imports
the `anthropic` SDK directly, so swapping providers or adding a second one
never touches calling code. Caching (`cache_service.py`) and rate limiting
(`core/rate_limit.py`) sit at the API layer, wrapping `analyze_code()`
rather than living inside `analysis_service.py` — the deterministic
pipeline itself has no idea Redis exists, same principle as the
database/AI isolation above. The Celery tasks (`app/tasks/analysis_tasks.py`,
`app/tasks/github_tasks.py`) call the identical `run_analysis()`/
`save_analysis_run()` functions the synchronous endpoint does — including
once per file for a repository — so there is exactly one analysis
implementation, not two or three.

## Technology stack

**Frontend:** React 18, Vite, Tailwind CSS, `@monaco-editor/react`,
React Router (with an auth context + route guard), Vitest + Testing Library.

**Backend:** Python 3.12, FastAPI, Pydantic v2, `cppcheck` (system binary),
`pyflakes`, `ast` (stdlib), `javalang`, Node.js + ESLint 9 (system tools),
SQLAlchemy 2 + Alembic + `psycopg2` (PostgreSQL), `python-jose` (JWT),
`passlib`+`bcrypt` (password hashing), `anthropic` (AI review, optional),
`redis` + `celery` (caching, rate limiting, background jobs), `httpx`
(GitHub API calls), Pytest + `fakeredis`.

**Database:** PostgreSQL. This project was developed and manually verified
end-to-end against a real local PostgreSQL 16 instance (`apt-get install
postgresql`, real `alembic upgrade head`, real rows inspected via `psql`).
The pytest suite instead uses an isolated in-memory SQLite database (see
`backend/tests/conftest.py`) purely so `pytest` never requires a running
Postgres server — Alembic's own migrations are Postgres-only.

**AI provider:** Anthropic's API, entirely optional (see
[Environment variables](#environment-variables)). Verified with two real
network calls to `api.anthropic.com` during development — one with an
intentionally invalid key confirming the real 401 response is caught and
converted to a graceful `AIServiceError`, and one exercising the full
`run_analysis()` pipeline the same way end-to-end. The success path (a
valid key returning real structured JSON) is covered by unit tests that
mock the Anthropic client's response object, since a real success call
isn't reproducible without a live paid API key.

**Redis / Celery:** Verified against a real local Redis 7 instance
(`apt-get install redis-server`) and a real, separately-running Celery
worker process during development — not just the eager-mode test suite.
Concretely: enqueued a task over HTTP, confirmed an independent worker
process received and executed it (visible in the worker's own log), and
confirmed a persisted async analysis landed correctly in real PostgreSQL.
The pytest suite instead runs Celery in eager mode (synchronous, in-process,
no broker needed) against `fakeredis`, for the same hermeticity reasons as
the SQLite test database above.

**Docker:** `docker-compose.yml` plus a `Dockerfile` in `backend/` and
`frontend/` are written and the compose YAML has been validated to parse
correctly, but **were not run through `docker compose up`** — this
project's sandbox had no Docker daemon available (see
[Running with Docker](#running-with-docker)). Every service in the compose
file mirrors a process configuration already proven working by running it
natively (Postgres, Redis, the backend, a Celery worker) during
development, but the compose file itself should be reviewed before trusting
it in production, same as any infra config you haven't personally run yet.

**GitHub API:** Real calls to `api.github.com` during development hit
GitHub's unauthenticated rate limit (60 requests/hour, shared across
everything using the same network egress in this project's dev sandbox)
before a full successful repository fetch could be exercised live. What
*was* verified live: a real 403 rate-limit response from GitHub's actual
API being caught and converted to a clean `GitHubServiceError` (the same
error-handling path a real "repo not found" or "rate limited" response
takes), and the real Celery worker correctly registering
`analyze_github_repo_task` alongside `analyze_code_task`. The full
fetch-and-analyze success path is covered by tests that mock
`fetch_repo_files` with realistic data and exercise the rest of the
pipeline (task execution, persistence, the aggregate report) for real — see
[Testing](#testing). If you have a `GITHUB_TOKEN` handy, the success path
is one real request away: `GITHUB_TOKEN=... ` in `.env` raises the limit to
5,000/hour.

## Project structure

```
codeinsight-ai/
├── .github/
│   └── workflows/
│       └── ci.yml           # runs backend pytest + frontend vitest/build on push/PR
├── backend/
│   ├── app/
│   │   ├── api/            # routing only: analyze.py, auth.py, projects.py,
│   │   │                   # tasks.py (Phase 5 async endpoints), github.py
│   │   │                   # (Phase 6 repo analysis), health.py
│   │   ├── core/           # config.py, security.py (hashing/JWT), deps.py (auth
│   │   │                   # dependencies), time.py, logging_config.py,
│   │   │                   # redis_client.py, rate_limit.py (Phase 5)
│   │   ├── schemas/        # enums.py (shared Language/Severity/Category/
│   │   │                   # FindingSource), analysis.py, ai_review.py,
│   │   │                   # user.py, project.py, github.py (Phase 6 report/
│   │   │                   # analytics schemas) — Pydantic contracts
│   │   ├── services/       # analysis_service.py, scoring_service.py,
│   │   │                   # history_service.py (DB persistence bridge +
│   │   │                   # Phase 6 analytics aggregation),
│   │   │                   # ai_service.py (AI provider abstraction),
│   │   │                   # cache_service.py (Phase 5 Redis cache),
│   │   │                   # github_service.py (Phase 6 repo fetching)
│   │   ├── analyzers/      # base.py, cpp_analyzer.py, python_analyzer.py,
│   │   │                   # javascript_analyzer.py, java_analyzer.py,
│   │   │                   # complexity_analyzer.py, language_detector.py
│   │   ├── models/         # user.py, project.py, file.py, analysis_run.py,
│   │   │                   # finding.py, recommendation.py (SQLAlchemy ORM)
│   │   ├── database/       # session.py — engine, SessionLocal, get_db
│   │   ├── tasks/          # analysis_tasks.py (Phase 5), github_tasks.py
│   │   │                   # (Phase 6) — both Celery tasks
│   │   ├── celery_app.py   # Celery app instance (Phase 5)
│   │   └── main.py         # FastAPI app, CORS, secure headers, exception handlers
│   ├── alembic/             # migrations (env.py wired to app settings/models)
│   ├── tools/
│   │   └── js-lint/         # standalone ESLint install + fixed flat config
│   │                         # used by javascript_analyzer.py (NOT the
│   │                         # frontend's own lint setup)
│   ├── tests/               # pytest suite (77 tests) + sample_code.py fixtures
│   ├── Dockerfile           # backend + Celery worker image (Phase 5)
│   ├── .dockerignore
│   ├── alembic.ini
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── src/
│   │   ├── components/     # Navbar, RequireAuth, SeverityBadge, FindingCard,
│   │   │                   # ScorePanel, SeverityBar, CategoryFilter,
│   │   │                   # AIReviewPanel, AnalysisResultsPanel (shared by
│   │   │                   # Analyzer + History), GitHubImportPanel (Phase 6)
│   │   ├── context/         # AuthContext.jsx — JWT/user state
│   │   ├── pages/           # Landing, CodeAnalyzer (+ test), Login, Register,
│   │   │                   # Projects, History, Analytics (Phase 6)
│   │   ├── services/        # api.js — fetch wrapper, no UI logic
│   │   ├── App.jsx, main.jsx, index.css
│   ├── vite.config.js       # dev proxy: /api -> http://localhost:8000
│   ├── Dockerfile           # multi-stage build -> nginx (Phase 5)
│   ├── nginx.conf           # serves the SPA, proxies /api to the backend service
│   ├── .dockerignore
│   ├── tailwind.config.js
│   └── package.json
├── docs/
├── docker-compose.yml       # postgres + redis + backend + celery_worker + frontend
├── .env.example
├── .gitignore
└── README.md
```

## Installation

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ running locally (or point `DATABASE_URL` at any reachable
  instance)
  - macOS: `brew install postgresql@16 && brew services start postgresql@16`
  - Ubuntu/Debian: `sudo apt-get install postgresql postgresql-contrib`
  - Windows: install via the [PostgreSQL installer](https://www.postgresql.org/download/windows/)
- Redis 6+ running locally (or point `REDIS_URL` at any reachable
  instance). Optional in the sense that caching/rate limiting/Celery all
  fail open or simply don't run without it — but `POST /api/analyze/async`
  and the Celery worker need a real Redis to function.
  - macOS: `brew install redis && brew services start redis`
  - Ubuntu/Debian: `sudo apt-get install redis-server`
  - Windows: use [Memurai](https://www.memurai.com/) or WSL
- `cppcheck` on your `PATH` (C++ analysis silently degrades to an
  "analyzer unavailable" info-level finding if it's missing — it never
  fakes results)
  - macOS: `brew install cppcheck`
  - Ubuntu/Debian: `sudo apt-get install cppcheck`
  - Windows: install via the [cppcheck releases page](https://cppcheck.sourceforge.io/)
- A JDK (not just a JRE) on your `PATH` for Java analysis — `javac` must be
  callable. Java analysis degrades to an "analyzer unavailable" finding if
  it's missing.
  - macOS: `brew install openjdk@21`
  - Ubuntu/Debian: `sudo apt-get install openjdk-21-jdk-headless`
  - Windows: install [Temurin](https://adoptium.net/) or another OpenJDK build

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../.env.example ../.env
# Edit .env: set SECRET_KEY to a real random value and DATABASE_URL to your
# Postgres connection string (a working default is already filled in for a
# local `codeinsight`/`codeinsight` database -- create that DB and role, or
# change the URL to match whatever you have).

# Create the schema (run once, and again after pulling any new migration):
alembic upgrade head

# JavaScript analysis uses a standalone ESLint install (separate from the
# frontend's own tooling) -- install it once:
cd tools/js-lint
npm install
cd ../..
```

### Frontend
```bash
cd frontend
npm install
```

## Environment variables

See [`.env.example`](./.env.example). `DATABASE_URL` and `SECRET_KEY` now
matter for real use (the defaults are a working local-Postgres URL and an
insecure placeholder key, respectively — change `SECRET_KEY` before you
rely on the JWTs it signs for anything). `REDIS_URL` matters for caching,
rate limiting, and Celery (see [Installation](#installation)). `GITHUB_TOKEN`
is optional — GitHub repository analysis works against public repos without
it (subject to GitHub's 60-requests/hour unauthenticated rate limit);
setting it raises that to 5,000/hour and allows private repos. Everything
else still has a safe development default in `backend/app/core/config.py`.
The file documents the AI API key too, so nobody is tempted to hardcode a
secret later.

## Running locally

**Terminal 1 — backend (from `backend/`):**
```bash
uvicorn app.main:app --reload --port 8000
```
Visit `http://localhost:8000/docs` for interactive OpenAPI docs.

**Terminal 2 — frontend (from `frontend/`):**
```bash
npm run dev
```
Visit `http://localhost:5173`. The Vite dev server proxies `/api/*` to
`http://localhost:8000`, so no CORS configuration is needed in development.

**Terminal 3 — Celery worker (from `backend/`, optional):**
```bash
celery -A app.celery_app.celery_app worker --loglevel=info
```
Only needed if you want to use `POST /api/analyze/async` /
`GET /api/tasks/{id}`. The synchronous `POST /api/analyze` works without
this terminal running at all. Requires a reachable Redis (`REDIS_URL`).

## Running with Docker

```bash
cp .env.example .env   # edit SECRET_KEY at minimum
docker compose up --build
```
Brings up Postgres, Redis, the backend, a Celery worker, and the frontend
(nginx serving the built React app, proxying `/api/` to the backend) —
frontend at `http://localhost:5173`, API docs at
`http://localhost:8000/docs`. See `docker-compose.yml`'s own header comment
for an important caveat: **this compose file was written but not run
through `docker compose up`** in the sandbox this project was developed in
(no Docker daemon available there) — every service mirrors a configuration
already proven to work by running the equivalent processes natively (see
[Technology stack](#technology-stack)), but review it yourself before
relying on it, the same caution you'd apply to any infra config you
haven't personally run.

## API documentation

Full interactive docs are auto-generated by FastAPI at `/docs` and `/redoc`
once the backend is running. Summary of current endpoints:

| Method | Path | Auth? | Description |
|---|---|---|---|
| GET | `/api/health` | no | Health check + which analyzers are available |
| POST | `/api/auth/register` | no | Create an account |
| POST | `/api/auth/login` | no | Exchange email+password for a JWT |
| GET | `/api/users/me` | yes | The authenticated user's profile |
| POST | `/api/projects` | yes | Create a project |
| GET | `/api/projects` | yes | List your projects |
| GET | `/api/projects/{id}` | yes | Get one of your projects (404 if not yours) |
| DELETE | `/api/projects/{id}` | yes | Delete one of your projects |
| GET | `/api/projects/{id}/analytics` | yes | Score trend, severity totals, top rule ids, language breakdown, worst files across every persisted run in the project (404 if not yours) |
| POST | `/api/analyze` | optional | Run static + complexity analysis. Include `project_id` (and a valid token for that project's owner) to persist the result; add `"include_ai_review": true` to also get an AI explanation layer (opt-in, degrades gracefully with no API key); omit all three to get the original Phase 1/2 anonymous, unsaved behavior. Rate-limited per IP; identical requests are served from cache |
| POST | `/api/analyze/async` | optional | Same request body and behavior as `POST /api/analyze`, but runs on a Celery worker and returns `202` with a `task_id` immediately instead of blocking |
| GET | `/api/tasks/{task_id}` | no | Poll a background analysis task: `{"status": "pending"\|"started"\|"success"\|"failure", "result": ..., "error": ...}` |
| GET | `/api/analysis/{id}` | yes | Fetch one persisted analysis run (404 if not yours) |
| GET | `/api/analysis/history` | yes | List your persisted runs, optionally `?project_id=` filtered |
| POST | `/api/github/analyze` | yes | Fetch and analyze every supported source file in a GitHub repo, persisting each as its own run under `project_id`. Always async — returns `202` + `task_id` |
| GET | `/api/github/analyze/{task_id}` | no | Poll a repository analysis task; on success, `result` is an aggregate report (`files_analyzed`, `average_score`, per-file summaries, etc.) |

Send `Authorization: Bearer <token>` (from `/api/auth/login`) on any
"yes"/"optional" endpoint above. `POST /api/analyze`/`/async` and
`POST /api/auth/login` are rate-limited per client IP (429 once exceeded;
configurable/disableable via `.env`, see `RATE_LIMIT_*`).

**Example request (anonymous, not persisted — same as Phase 1/2):**
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
        "code": "def process(items, cache={}):\n    cache[len(items)] = items\n    return cache\n",
        "language": "python"
      }'
```

**Example response (trimmed):**
```json
{
  "language": "python",
  "findings": [
    {
      "rule_id": "mutable-default-argument",
      "category": "bug",
      "severity": "medium",
      "message": "Function 'process' uses a mutable default argument.",
      "explanation": "Mutable default arguments are created once at function-definition time and shared across all calls.",
      "why_it_matters": "Mutating the default in one call silently leaks state into every future call.",
      "suggestion": "Use `None` as the default and create the mutable object inside the function body.",
      "source": "static-analysis"
    }
  ],
  "complexity": { "time_complexity": "O(1)", "space_complexity": "O(1)", "is_estimated": true },
  "score": { "total": 97, "base": 100, "bug_penalty": 3, "security_penalty": 0, "complexity_penalty": 0, "maintainability_penalty": 0 },
  "summary": "1 issue(s) found by static analysis. Quality score: 97/100.",
  "analysis_id": null,
  "ai_review": null
}
```

**Example request (authenticated, persisted to a project):**
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-password"}' | python3 -c "import json,sys;print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"code": "...", "language": "python", "filename": "utils.py", "project_id": 1}'
# response is identical in shape, but "analysis_id" is now a real integer,
# and the run is retrievable later via GET /api/analysis/{that id}
```

**Example request (with the opt-in AI review layer, requires `ANTHROPIC_API_KEY`):**
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"code": "...", "language": "python", "include_ai_review": true}'
```
```json
{
  "...": "... same findings/score/complexity as above, plus:",
  "findings": [
    "... deterministic findings ...",
    {
      "rule_id": "ai-suggested-issue",
      "category": "bug",
      "severity": "medium",
      "message": "Possible off-by-one in the loop bound",
      "explanation": "The loop may run one iteration too many for empty input.",
      "suggestion": "Double check the intended range.",
      "source": "ai"
    }
  ],
  "ai_review": {
    "summary": "The function is small and mostly fine.",
    "overall_assessment": "Low risk overall, one logic concern worth a look.",
    "recommendations": [
      { "title": "Add a docstring", "description": "Explain what the function returns and its edge cases." }
    ],
    "improved_code": "def process(items, cache=None):\n    if cache is None:\n        cache = {}\n    ..."
  }
}
```
If `ANTHROPIC_API_KEY` isn't configured (or the call fails for any reason),
the response looks like the first example plus one extra finding:
`{"rule_id": "ai-review-unavailable", "source": "ai", "severity": "info", ...}`
— the request still returns `200`, `ai_review` stays `null`, and every
deterministic result is completely unaffected.

**Example request (background/async, requires a Celery worker running):**
```bash
curl -X POST http://localhost:8000/api/analyze/async \
  -H "Content-Type: application/json" \
  -d '{"code": "...", "language": "python"}'
# -> 202 {"task_id": "84352b2f-...", "status": "pending"}

curl http://localhost:8000/api/tasks/84352b2f-...
# -> 200 {"task_id": "84352b2f-...", "status": "success", "result": {...same shape as POST /api/analyze...}}
```

**Example request (GitHub repository analysis, requires a Celery worker):**
```bash
curl -X POST http://localhost:8000/api/github/analyze \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"repo_url": "owner/repo", "project_id": 1}'
# -> 202 {"task_id": "9c1f...", "status": "pending"}

curl http://localhost:8000/api/github/analyze/9c1f...
```
```json
{
  "task_id": "9c1f...",
  "status": "success",
  "result": {
    "repo": "owner/repo",
    "default_branch": "main",
    "files_analyzed": 8,
    "files_skipped": 2,
    "truncated": false,
    "average_score": 91.4,
    "critical_count": 0,
    "high_count": 3,
    "medium_count": 5,
    "low_count": 2,
    "info_count": 0,
    "files": [
      { "path": "src/utils.py", "language": "python", "analysis_id": 42, "score_total": 88, "critical_count": 0, "high_count": 1 }
    ]
  }
}
```
Each file in `files` was persisted as its own analysis run under
`project_id` — `GET /api/analysis/history?project_id=1` and
`GET /api/analysis/{analysis_id}` work on them exactly like any other
saved analysis.

**Example request (project analytics):**
```bash
curl http://localhost:8000/api/projects/1/analytics -H "Authorization: Bearer $TOKEN"
```
```json
{
  "project_id": 1,
  "total_runs": 8,
  "average_score": 91.4,
  "language_breakdown": { "python": 8 },
  "severity_totals": { "high": 3, "medium": 5 },
  "top_rule_ids": [{ "rule_id": "mutable-default-argument", "count": 2 }],
  "score_trend": [{ "analysis_id": 40, "filename": "src/main.py", "language": "python", "created_at": "...", "score_total": 95 }],
  "worst_files": [{ "analysis_id": 42, "filename": "src/utils.py", "language": "python", "created_at": "...", "score_total": 88 }]
}
```

## Testing

**Backend (77 tests, all passing):**
```bash
cd backend
pytest -v
```
Runs against an isolated in-memory SQLite database (see
`tests/conftest.py`), so no Postgres server is required to run the suite —
and likewise against `fakeredis` and Celery's eager mode, so no Redis
server or worker process is required either. Covers: health check, C++
findings (array-out-of-bounds, null dereference, clean code has none),
Python findings (mutable default, eval/bare-except, undefined name, syntax
errors reported as critical), JavaScript findings (eval/loose equality,
unused vars/async-promise-executor, clean code scores highly, syntax
errors reported as critical), Java findings (empty catch/resource leak,
hardcoded credentials, clean code scores highly, compile errors surfaced
with `source: "compiler"`), complexity estimation, score calculation on
clean code, request validation (empty code, invalid language, oversized
payload), and that internal errors never leak a stack trace to the client
— plus, from Phase 3: register/login (including duplicate-email and
wrong-password rejection), password length validation, `/users/me` auth
enforcement, project CRUD scoped strictly to the owner (a project id
belonging to another user always 404s), analyze-and-persist end-to-end
(including that the retrieved detail's findings/score exactly match what
the original request returned), anonymous analyze staying unsaved,
persistence being rejected for a `project_id` you don't own, and history
correctly filtering by project — plus, from Phase 4: provider selection (no
key -> `NullAIProvider`, key present -> `AnthropicAIProvider`) without a
network call, response parsing/validation against valid JSON, JSON wrapped
in markdown fences, invalid JSON, and JSON missing required fields,
`include_ai_review=false` never attempting AI at all, graceful degradation
to one INFO finding with no API key configured, a mocked successful AI
review correctly merging `additional_issues` into `findings`
(`source: "ai"`) and populating `ai_review`, AI-sourced findings being
weighted at half severity in scoring, and AI recommendations round-tripping
through persistence — plus, from Phase 5: identical requests being served
from cache (asserted by counting real `run_analysis()` invocations, not
just response equality), different code never hitting the cache, a
simulated Redis outage during caching failing open instead of failing the
request, `/api/analyze` and `/api/auth/login` returning 429 once their
configured per-minute limit is exceeded, rate limiting being disableable,
secure headers present on normal responses and CSP correctly skipped on
`/docs`, and the full async task lifecycle (enqueue → poll → success,
oversized payload rejected before enqueueing, `project_id` without auth
rejected, and persistence working identically to the synchronous endpoint)
— plus, new in Phase 6: `parse_repo_slug` accepting every documented URL
format and rejecting garbage, the full GitHub-analysis task lifecycle with
a mocked `fetch_repo_files` (enqueue → poll → success, each file persisted
as its own analysis run, `files_skipped` surfaced correctly), a
`GitHubServiceError` from the fetch layer surfacing as a clean task
failure message rather than a raw exception, a repo import being rejected
for a `project_id` you don't own, and project analytics correctly
aggregating multiple runs (language breakdown, top rule ids, score trend,
worst files) as well as returning a sane empty result for a project with
no runs yet.

Some things are deliberately *not* covered by pytest, and were instead
verified manually against real infrastructure during development (see
[Technology stack](#technology-stack)): two live network calls to the real
Anthropic API (an intentionally invalid key producing a real error that's
caught and converted gracefully, both directly and through the full
pipeline), the full Celery flow with an actually separate worker process
connected to real Redis — enqueueing a task over HTTP, confirming an
independent process received and executed it, and confirming a persisted
async analysis landed correctly in real PostgreSQL — that same worker
correctly registering both `analyze_code_task` and
`analyze_github_repo_task`, a live 403 rate-limit response from the real
GitHub API being caught and converted to a clean `GitHubServiceError`, and
the analytics endpoint end-to-end against real PostgreSQL. A live AI
*success* call, a live GitHub repository fetch *success* (this project's
sandbox shares network egress with other traffic that had already
exhausted GitHub's 60-requests/hour unauthenticated limit — see
[Technology stack](#technology-stack)), and a live `docker compose up` are
the things not reproducible/available in this project's development
sandbox at all — each is covered instead by tests against realistic mocked
data for exactly the part that couldn't be exercised live.

**Frontend (4 tests, all passing):**
```bash
cd frontend
npm run test
```
Covers the Code Analyzer page's core rendering/empty-state behavior, that
all four languages appear in the selector, and that the AI review checkbox
is present and unchecked by default (Monaco is stubbed out in tests since
it doesn't render meaningfully in jsdom). Login/Register/Projects/History/
Analytics pages and the GitHub import panel don't have dedicated component
tests yet — they're covered indirectly by the backend tests exercising the
same endpoints they call.

## Code quality score

The score starts at 100 and subtracts an explainable penalty per category
(bugs, security, complexity, maintainability) based on the severity and
count of findings in that category — see `app/services/scoring_service.py`.
The full breakdown is returned in every response and shown in the UI, so a
score of "78/100" always comes with a visible "why." Findings with
`source: "ai"` count at **half** their severity's usual weight — an
unverified AI suggestion shouldn't move the score as much as a
deterministic tool's confirmed finding of the same severity (see
[Key design decisions](#key-design-decisions)).

## Security considerations

- Submitted code is **never executed**. C++ analysis passes code to
  `cppcheck` as a file argument (not through a shell); Python analysis uses
  `ast.parse`/`pyflakes`, which parse but do not execute source; JavaScript
  is piped to ESLint over stdin (parsed/linted, not run); Java is compiled
  with `javac` (compilation only — the resulting `.class` files are never
  executed) with `-proc:none` to disable annotation processing.
- `cppcheck`, ESLint, and `javac` all run as subprocesses with a hard
  timeout; a timeout degrades to an informational finding rather than
  hanging the request.
- Request size is capped (`MAX_CODE_SIZE_BYTES`, default 200 KB) and
  enforced before analysis runs.
- All internal exceptions are logged server-side and returned to the client
  as a generic 500 message — no stack traces are ever exposed. Pydantic
  validation errors are also sanitized through `jsonable_encoder` so an
  internal `ValueError` object in the error context can't crash the
  response.
- CORS is restricted to the known frontend origins in `core/config.py`.
- No secrets are hardcoded anywhere; `.env.example` documents every
  variable and `.env` is git-ignored.
- Passwords are hashed with bcrypt (never stored or logged in plaintext);
  `/api/auth/login` returns an identical error for "no such user" and
  "wrong password" so it can't be used to enumerate registered emails.
- JWTs are signed with `SECRET_KEY` (HS256) and expire after
  `ACCESS_TOKEN_EXPIRE_MINUTES` (default 24h). **Change `SECRET_KEY`** from
  the placeholder in `.env.example` before relying on this for anything —
  anyone with the placeholder key can forge tokens.
- Every project/analysis lookup is scoped to `current_user.id` at the query
  level (not filtered after the fact), and a resource that exists but isn't
  yours returns 404, never 403 — this avoids confirming another user's
  project or analysis id exists at all.
- The AI review layer sends submitted code to Anthropic's API only when a
  caller explicitly opts in (`include_ai_review: true`) *and*
  `ANTHROPIC_API_KEY` is configured — never by default, and never silently.
  The AI's JSON output is validated against a strict Pydantic schema before
  any of it is used; anything that fails to parse or validate is discarded
  entirely rather than partially trusted (see `app/services/ai_service.py`).
  AI-sourced findings are always tagged `source: "ai"` and never presented
  as guaranteed bugs.
- `POST /api/analyze`, `POST /api/analyze/async`, and
  `POST /api/auth/login` are rate-limited per client IP
  (`app/core/rate_limit.py`, Redis-backed, configurable/disableable via
  `.env`) — mitigates both abuse and runaway AI API spend, since an
  unthrottled `/api/analyze` with AI review enabled could otherwise run up
  a bill quickly.
- Baseline secure response headers (`X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`,
  `Strict-Transport-Security`, `Content-Security-Policy`) are set on every
  response (see `app/main.py`); CSP is skipped only on `/docs`/`/redoc` so
  Swagger UI keeps working.
- The Celery worker (background analysis) shares the same code path as the
  synchronous endpoint — `run_analysis()`/`save_analysis_run()` — so there
  is no second, separately-secured analysis implementation to audit.
- The Docker images run as a non-root user (`backend/Dockerfile`) and the
  frontend's build stage is discarded from the final nginx image (multi-
  stage build), so no Node.js toolchain or `node_modules` ships in the
  production frontend image.
- GitHub repository analysis never runs `git clone` or executes anything
  from the target repo — only the GitHub API (Git Trees + raw content) is
  used, and only text content of files matching a supported extension is
  ever read. A repo's size is bounded (`GITHUB_MAX_FILES`,
  `GITHUB_MAX_FILE_SIZE_BYTES`) so a single request can't be used to force
  the server into fetching or analyzing an unbounded amount of data.
  `POST /api/github/analyze` requires auth and an owned `project_id` — it
  can't be used to probe or persist data into a project you don't own, and
  it shares the same `rate_limit("analyze")` bucket as `/api/analyze`.
- Even with the above, this project still has no request/response logging
  redaction audit, no secrets manager integration, and (as ever) hasn't
  been through a real security review. **Treat it as a portfolio project,
  not a production-hardened service**, and review it yourself before
  deploying it anywhere that matters.

## Roadmap

All six planned phases are complete:

- ~~**Phase 2** — JavaScript/Java analyzers, richer results dashboard~~ ✅ done
- ~~**Phase 3** — PostgreSQL, user accounts, projects, analysis history~~ ✅ done
- ~~**Phase 4** — AI service abstraction (structured-JSON explanations,
  refactoring suggestions, validated via Pydantic)~~ ✅ done
- ~~**Phase 5** — Redis/Celery background processing, Docker Compose, rate
  limiting + secure headers~~ ✅ done (Docker Compose written and
  YAML-validated but not run through `docker compose up` — see
  [Technology stack](#technology-stack))
- ~~**Phase 6** — GitHub repository integration, advanced analytics~~ ✅ done
  (repository-fetch success path verified via realistic mocks rather than
  a live call, due to this sandbox's shared GitHub API rate limit — see
  [Technology stack](#technology-stack) and [Testing](#testing))

Ideas for beyond the original six phases, in no particular order and none
started: OAuth login (GitHub/Google) instead of email+password only, a
GitHub webhook to auto-analyze on push, per-organization/team accounts,
a diff-aware mode that only analyzes changed lines in a PR, and exporting
a report as PDF/Markdown.

## Key design decisions

- **Real linter over hand-rolled parser.** The C++ analyzer wraps
  `cppcheck` instead of implementing a fragile custom C++ parser, per the
  project's own rule to prefer existing tools where they exist. If
  `cppcheck` isn't installed, the API says so explicitly rather than
  silently returning zero findings.
- **Normalized `Finding` model as the contract.** Every analyzer — current
  and future (AI, compiler, complexity) — must produce the same shape, with
  a `source` field so the UI (and the user) always knows whether a claim is
  deterministic or AI-suggested.
- **Extension-safe temp files.** `cppcheck` identifies language from file
  extension, not content — so the analyzer always forces a `.cpp`-family
  extension on the temp file it writes, regardless of what filename the
  client sends. (This was caught by the test suite: the default filename
  had no extension, causing every submission to falsely report a
  `syntaxError` instead of the real findings.)
- **Complexity results are always labeled "estimated."** The estimator
  reasons about loop nesting depth and a few recognizable patterns; it does
  not — and cannot — prove exact algorithmic complexity from source alone.
- **ESLint over stdin, not a temp file.** ESLint 9's flat config refuses to
  lint files outside its own "base path" by default. Writing the submission
  to a temp file elsewhere silently produced a "file ignored" result instead
  of real findings; piping the code over stdin with `--stdin-filename`
  sidesteps that restriction entirely.
- **`javac` needs a filename matching the public class.** Java only enforces
  the "filename == public class name" rule for a top-level `public` type, so
  the analyzer regex-detects `public class/interface/enum/record Name` in
  the submission and names the temp file accordingly (falling back to
  `Submission.java` when there's no public type, which still compiles or
  produces a legitimate, informative compiler error).
- **`javalang`'s `CatchClause` nodes carry no position.** Line numbers for
  catch-clause findings (empty catch, overly broad exception type) are
  derived from the enclosing `TryStatement`'s position instead, since
  `javalang` never sets `.position` on `CatchClause`/`CatchClauseParameter`.
- **A pinned dependency was missing.** `pyflakes` (imported directly by
  `python_analyzer.py`) was never listed in `requirements.txt` — Phase 1's
  tests only passed because it happened to be preinstalled in the dev
  sandbox. Caught and fixed while auditing dependencies for Phase 2.
- **Anonymous analysis stays anonymous.** `project_id` on `POST /api/analyze`
  is optional; persistence is strictly opt-in so Phase 1/2's "no login
  required" behavior is preserved byte-for-byte for anyone who doesn't pass
  it. This was a deliberate constraint, not an accident — a required-auth
  redesign would have broken every existing test and use case for no
  benefit.
- **`get_current_user_optional` fails loudly on a bad token.** No token at
  all means anonymous access is fine; a token that's present but
  expired/malformed raises 401 instead of silently downgrading to
  "anonymous," which would otherwise hide a real auth problem from the
  caller (e.g. an expired session silently losing the ability to save).
- **404, never 403, on someone else's resource.** Every project/analysis
  lookup in `history_service.py` and `app/api/projects.py` checks ownership
  as part of the query itself (`WHERE owner_id = current_user.id`), so a
  wrong-owner id is indistinguishable from a nonexistent one — this avoids
  leaking which ids exist to an authenticated-but-unauthorized caller.
- **The full score breakdown is persisted, not just the total.** An early
  version of `AnalysisRun` only stored `score_total`; reconstructing a
  saved run's `ScoreBreakdown` from that alone would have silently
  fabricated all four penalty fields as zero. Caught before it shipped by
  reasoning through what `GET /api/analysis/{id}` needed to return, and
  fixed by adding real columns for each penalty category.
- **`bcrypt` needed an explicit pin.** `passlib[bcrypt]==1.7.4` probes
  `bcrypt.__about__.__version__`, which `bcrypt>=4.1` removed — password
  hashing failed outright (not just a warning) until `bcrypt==4.0.1` was
  pinned alongside it.
- **SQLite for tests, real Postgres for everything else.** The pytest suite
  overrides `get_db` with an isolated in-memory SQLite database so `pytest`
  never requires a running Postgres server. This is a test-hermeticity
  choice, not a claim that the app supports SQLite in production — Alembic's
  migrations are Postgres-only, and this project was manually verified
  end-to-end (register → login → create project → analyze → persist →
  retrieve, with rows inspected directly via `psql`) against a real local
  PostgreSQL 16 instance during development.
- **AI review is opt-in, not automatic.** `include_ai_review` defaults to
  `false`. A real API call costs money and adds latency, and defaulting it
  to `true` would mean every existing caller (including the 41 Phase 1-3
  tests) silently starts paying for and waiting on an AI call the moment
  someone configures `ANTHROPIC_API_KEY` for local dev. Deterministic
  static analysis always runs regardless of this flag; only the AI layer
  is gated.
- **AI-sourced findings are weighted at half severity in scoring.** The
  project's own rule is "do not claim an AI prediction is a guaranteed
  bug" — letting an unverified AI-spotted "critical" issue move the score
  exactly as much as cppcheck/ESLint/javac confirming one would contradict
  that. Halving the weight (`app/services/scoring_service.py`) keeps AI
  input meaningful without treating it as equally certain.
- **A circular import was caught while wiring the AI schema in.**
  `ai_review.py` needed `Category`/`Severity` from `analysis.py`, and
  `analysis.py` needed `AIReviewSummary` from `ai_review.py` — a genuine
  cycle, not just an import-order nuisance. Fixed by extracting the shared
  enums into `app/schemas/enums.py`, which both modules import from
  instead of each other.
- **The AI layer never fails the request.** Every failure mode — no key
  configured, a real API error, a timeout, malformed JSON, or JSON that
  doesn't match the expected schema — is caught in
  `app/services/ai_service.py` and converted into a single INFO-level
  "ai-review-unavailable" finding by `analysis_service.py`, mirroring how
  a missing `cppcheck`/ESLint/`javac` already degrades gracefully rather
  than fabricating a result. Verified with two real network calls to
  `api.anthropic.com` during development (see
  [Technology stack](#technology-stack)), not just mocks.
- **Redis is optional infrastructure, not a hard dependency.** Caching and
  rate limiting both fail open on any `redis.RedisError` — a Redis outage
  means "skip the optimization" (fresh computation) or "skip the limit"
  (request allowed through), never a failed request. This mirrors the same
  philosophy already established for `cppcheck`/ESLint/`javac`/the AI
  provider all being optional: infrastructure that isn't there degrades
  the experience, it doesn't break it.
- **A custom rate limiter instead of a third-party library.** For a
  project this size, a ~30-line Redis `INCR`+`EXPIRE` fixed-window
  implementation (`app/core/rate_limit.py`) is easier to read and audit in
  full than pulling in a new dependency, and it doubles as a second
  concrete, real use of Redis alongside caching rather than a decorative
  one.
- **The Celery task calls the exact same functions the synchronous
  endpoint does.** `app/tasks/analysis_tasks.py` has no analysis logic of
  its own — it calls `run_analysis()` and `save_analysis_run()`, the same
  functions `app/api/analyze.py` calls directly. There is exactly one
  implementation of "run an analysis," not a synchronous one and a
  separately-maintained background one that could drift apart.
- **`SessionLocal` is imported inside the Celery task's function body, not
  at module level.** A top-level `from app.database.session import
  SessionLocal` would bind that name once, at import time, in the task
  module's own namespace — permanently pointing at whatever engine was
  configured when the module first loaded. Importing it inside the
  function instead means `tests/conftest.py` can monkeypatch
  `app.database.session.SessionLocal` (the same technique used for the
  SQLite test database) and have the Celery task actually pick it up,
  rather than silently talking to a real Postgres the test environment
  doesn't have.
- **Celery's `include=` mechanism, not an implicit import at the bottom of
  `celery_app.py`.** The natural-looking fix for "the worker doesn't know
  about `analyze_code_task`" is `import app.tasks.analysis_tasks` at the
  bottom of `celery_app.py` — but that file is exactly what
  `analysis_tasks.py` imports `celery_app` *from*, so it's a real circular
  import, not just an ordering nuisance. Caught by actually starting a
  real `celery worker` process and finding `[tasks]` printed empty on
  startup; fixed with the `include=["app.tasks.analysis_tasks"]` argument
  Celery provides for exactly this.
- **Celery's eager-mode result storage isn't on by default.** Tests run
  Celery in eager mode (synchronous, in-process) for speed and
  hermeticity, but `AsyncResult(...).result` came back empty until
  `task_store_eager_result = True` was added to the test config — eager
  mode normally skips writing to the result backend at all. Caught by a
  failing assertion, not by inspection.
- **GitHub repository analysis reuses `run_analysis()`/
  `save_analysis_run()` per file, rather than being a separate analysis
  path.** `app/tasks/github_tasks.py` has no analysis logic of its own; it
  fetches files, then calls the exact same functions the single-file
  synchronous and async endpoints call, once per file. A repository
  analysis is "N ordinary analyses persisted under one project," not a
  fourth implementation of "analyze some code" to keep in sync with the
  other three.
- **The GitHub API, not `git clone`.** Fetching via the Git Trees API
  (file listing) and `raw.githubusercontent.com` (file content) means the
  server's filesystem is never touched by repository contents beyond the
  handful of files actually selected for analysis, and nothing from the
  repo is ever executed — consistent with every other analyzer's "parse or
  compile, never run" rule (see [Security considerations](#security-considerations)).
- **Repository size is bounded, and the bound is surfaced, not hidden.**
  `GITHUB_MAX_FILES` caps how many files a single request analyzes, and if
  GitHub's own tree listing itself gets truncated (an unusually large
  repo), `GitHubAnalysisReport.truncated` reports that explicitly rather
  than silently analyzing a partial repo and calling it complete.
- **Analytics required no new tables.** `get_project_analytics()` is pure
  aggregation over `AnalysisRun`/`FindingRecord` rows that persistence
  (Phase 3) was already writing — score trend, severity totals, and rule
  frequency are all derivable from data that already existed, so Phase 6
  added a read path, not a write path or a migration.
- **The GitHub repository-fetch success path is verified with realistic
  mocked data, not a live call — stated plainly, not glossed over.** This
  project's development sandbox shares its network egress with other
  traffic, which had already exhausted GitHub's 60-requests/hour
  unauthenticated rate limit before a full fetch-and-analyze cycle could
  be exercised live. What *was* verified live: a real 403 from GitHub's
  actual API being caught and converted to a clean `GitHubServiceError`
  (proving the error-handling path works against the real API, not just a
  mock of it), and a real Celery worker correctly registering
  `analyze_github_repo_task`. The gap this leaves is specifically "does
  parsing a real GitHub tree/blob response work" — everything downstream
  of that (task orchestration, persistence, the aggregate report) is
  exercised for real by the test suite against realistic fixture data.
