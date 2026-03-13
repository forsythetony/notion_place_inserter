# Notion Place Inserter

Accepts unstructured text (e.g. `"stone arch bridge in minneapolis"`), uses AI + Google Places API to gather structured data, and inserts a rich record into a Notion "Places to Visit" database. Uses a staged pipeline framework with TTL-based schema caching. Deploys to [Render](https://render.com) via Blueprint.

## Getting Started

### Prerequisites

- **Python 3.11+**
- **GitHub account** — for hosting the repository
- **Render account** — sign up at [dashboard.render.com](https://dashboard.render.com)

### Google Places API

The app uses the [Google Places API (New)](https://developers.google.com/maps/documentation/places/web-service) for place search and optional Place Details (for richer Notes descriptions). To obtain an API key:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable billing for your project (required for the Places API)
4. Enable the **Places API (New)** under **APIs & Services** → **Library**
5. Create an API key under **APIs & Services** → **Credentials** → **Create Credentials** → **API Key**
6. (Recommended) Restrict the key to the Places API only to limit exposure
7. Add `GOOGLE_PLACES_API_KEY=your-key-here` to `envs/local.env`

### Freepik Icons API (optional)

Page icons are resolved via the [Freepik Icons API](https://docs.freepik.com/api-reference/icons/get-all-icons-by-order). Claude generates a search term from the place context, and the first Freepik result is used.

When `DRY_RUN=1`, the icon pipeline falls back to a Claude-selected emoji if Freepik is unavailable (for example, `FREEPIK_API_KEY` is not set) or returns no result, so the dry-run table still shows an icon preview.

During normal (non-dry-run) page creation, if `FREEPIK_API_KEY` is not set or Freepik returns no result, the page icon is left blank. To enable Freepik:

1. Create an API key at [Freepik for Developers](https://www.freepik.com/api)
2. Add `FREEPIK_API_KEY=your-key-here` to `envs/local.env`

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/notion_place_inserter.git
   cd notion_place_inserter
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   make install
   # or: pip install -r requirements.txt
   ```

4. **Set the secret** (optional for local dev — defaults to `dev-secret`)
   ```bash
   export SECRET=your-local-secret
   ```

5. **Run the server**
   ```bash
   make run
   # or: make run-async   # async locations (default)
   # or: make run-sync    # synchronous locations (LOCATIONS_ASYNC_ENABLED=0)
   # or: uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   The app will be available at `http://localhost:8000`. By default, POST `/locations` returns immediately with `{status: "accepted", job_id: "..."}`; the pipeline runs in a background worker. Use `make run-sync` for synchronous behavior.

   **Async locations (dual process):** When `LOCATIONS_ASYNC_ENABLED=1` (default) and Supabase is configured, run both the API and the worker process. In one terminal: `make run` (or `make run-async`). In another: `make run-worker`. The worker consumes from the Supabase queue and persists run lifecycle transitions. Optional env: `WORKER_POLL_INTERVAL_SECONDS` (default 1), `WORKER_VT_SECONDS` (default 300).

6. **Dry-run mode** (optional) — validate property values without creating Notion pages:
   ```bash
   make run-dry-run
   ```
   Or set `DRY_RUN=1` in `envs/local.env`. POST `/locations` and POST `/test/randomLocation` will return a preview payload (`mode`, `database`, `properties`, `summary`) instead of creating pages. The server console also prints a formatted table of resolved properties for easier debugging.

### Supabase (Local Stack and Migrations)

The project uses Supabase for local database and migration-driven schema management. This is required for Phase 1 platform migration work.

**Prerequisites:** [Supabase CLI](https://supabase.com/docs/guides/cli) and [Docker](https://docs.docker.com/get-docker/) (for local Postgres, Auth, etc.).

**Install Supabase CLI:**
```bash
# macOS (Homebrew)
brew install supabase/tap/supabase

# Or via npm
npm install -g supabase
```

**Local stack lifecycle:**
```bash
make supabase-start    # Start local Supabase (Postgres, Studio, etc.)
make supabase-status   # Show service URLs and status
make supabase-stop     # Stop the stack
make supabase-reset    # Reset DB and reapply all migrations
```

**Migration workflow:**
- Schema changes must be migration files in `supabase/migrations/`, reviewed via PR.
- Create a new migration: `make supabase-migration-new NAME=<description>` (e.g. `NAME=add_users_table`).
- Migrations use the format `YYYYMMDDHHmmss_<name>.sql`. Apply with `make supabase-reset` or on first `supabase start`.

### Testing Locally

With the server running in another terminal:

```bash
# Without auth — expect 401 Unauthorized
curl http://localhost:8000/

# With auth — expect 200 and {"message": "Hello there!"}
curl -H "Authorization: dev-secret" http://localhost:8000/
```

Or use the Makefile (server must be running):

```bash
make test
# With custom secret: make test SECRET=your-secret
```

### Tavern API Tests

The `http-test/` folder contains [Tavern](https://tavern.readthedocs.io/)-style API tests. With the server running, source env and run:

```bash
set -a && source envs/local.env && set +a && make test-api
```

See [http-test/README.md](http-test/README.md) for configuration and usage.

### Deploying to Render

Use this sequence to validate locally, then deploy with Render Blueprint.

1. **Create your local env file**
   ```bash
   cp envs/env.template envs/local.env
   ```
   Fill in the required values in `envs/local.env` (see table below).

2. **Install dependencies and run local checks**
   ```bash
   make install
   set -a && source envs/local.env && set +a && make test-api
   ```

3. **Start the app locally and smoke test auth**
   ```bash
   make run
   make test SECRET=your-local-secret
   ```
   `your-local-secret` must match the `SECRET=` value in `envs/local.env`.

4. **Commit and push to GitHub**
   ```bash
   git add .
   git commit -m "Prepare Render deployment docs and config"
   git push origin main
   ```

5. **Create the Render service from Blueprint**
   - Open [dashboard.render.com](https://dashboard.render.com)
   - Create an environment group `notion-pipeliner-backend` with a secret file `.env` containing your production env (see [.env file loading](#env-file-loading) below)
   - Click **New** -> **Blueprint**
   - Select this repo; Render reads `render.yaml` and creates `notion-pipeliner-api` and `notion-pipeliner-worker`
   - Both services link to `notion-pipeliner-backend` (Blueprint uses `fromGroup` in `render.yaml`)
   - Scale worker to at least 1 instance

6. **Set environment variables**

   All required vars (SECRET, SUPABASE_*, provider keys, CORS_ALLOWED_ORIGINS, etc.) go in the env group or in the secret file. See the table below.

7. **Verify the deployed API**
   ```bash
   export BASE_URL="https://notion-pipeliner-api.onrender.com"
   export SECRET="YOUR_RENDER_SECRET"
   curl -H "Authorization: $SECRET" "$BASE_URL/"
   ```
   Expected response: `{"message":"Hello there!"}`.

   For full deployment steps, see [PR-06 Detailed Deploy Steps](docs/planning/multi-tenant-productization-prd/technical/phase-1-platform-migration/pr-06-detailed-deploy-steps.md).

#### Render Environment Variables

| Variable | Required | Default | Example | What it does |
|---|---|---|---|---|
| `SECRET` | Yes | Empty (`""`) | `super-long-random-string` | Authorization secret checked against the `Authorization` header on protected routes. |
| `NOTION_API_KEY` | Yes | None (must be set) | `secret_xxx` | Authenticates Notion API calls to read database schema and create pages. |
| `ANTHROPIC_TOKEN` | Yes | None (must be set) | `sk-ant-...` | API key for Claude-based text generation/classification in the pipeline. |
| `GOOGLE_PLACES_API_KEY` | Yes | None (must be set) | `AIza...` | Enables Google Places search/details lookups used for place enrichment. |
| `FREEPIK_API_KEY` | No | Unset | `fpk_...` | Enables Freepik icon lookup; if missing, icon may be blank in non-dry-run mode. |
| `DRY_RUN` | No | Disabled (`0`/false) | `1` or `0` | When truthy (`1/true/yes`), returns preview payloads instead of writing to Notion. |
| `LOCATIONS_ASYNC_ENABLED` | No | `1` (async) | `1` or `0` | When `1`, POST `/locations` enqueues to Supabase and returns immediately with `job_id`; pipeline runs in worker process (run `make run-worker` alongside API). When `0`, runs synchronously. |
| `WORKER_POLL_INTERVAL_SECONDS` | No | `1` | `1` | Worker poll interval when queue is empty. |
| `WORKER_VT_SECONDS` | No | `300` | `300` | Queue message visibility timeout (seconds); pipeline can take several minutes. |
| `GOOGLE_PLACE_DETAILS_FETCH` | No | `1` | `1` | Set `0` to skip optional Place Details requests (fewer API calls, less rich notes). |
| `LOCATIONS_CACHE_TTL_SECONDS` | No | `1800` | `1800` | TTL for cached existing-location index used in relation matching. |
| `LOCATION_MATCH_MIN_CONFIDENCE` | No | `0.85` | `0.85` | Minimum similarity score required before linking to an existing location. |
| `LOCATION_RELATION_REQUIRED` | No | `0` | `0` | Set `1` to fail the request if relation resolution fails; default is best-effort. |
| `LOG_FILE_PATH` | No | `logs/app.log` | `logs/app.log` | Log file output path for application logs. |
| `LOG_FILE_ROTATION` | No | `10 MB` | `10 MB` | Maximum log file size before rotation. |
| `LOG_FILE_RETENTION` | No | `3` | `3` | Number of rotated log files to retain. |
| `TWILIO_ACCOUNT_SID` | No | Unset | `AC...` | Twilio Account SID for WhatsApp run-status notifications. When async enabled and all Twilio vars set, success/failure messages are sent to `WHATSAPP_STATUS_RECIPIENT_DEFAULT`. |
| `TWILIO_AUTH_TOKEN` | No | Unset | `...` | Twilio Auth Token. |
| `TWILIO_WHATSAPP_NUMBER` | No | Unset | `whatsapp:+14155238886` | Twilio WhatsApp sender (sandbox or production). |
| `WHATSAPP_STATUS_RECIPIENT_DEFAULT` | No | Unset | `whatsapp:+1XXXXXXXXXX` | Fallback recipient for run-status messages. Required for notifications when Twilio is configured. |
| `WHATSAPP_STATUS_ENABLED` | No | `1` | `1` or `0` | Set `0` to disable WhatsApp notifications without removing Twilio credentials. |
| `WHATSAPP_STATUS_MAX_ERROR_CHARS` | No | `300` | `300` | Max characters for error text in failure messages; longer errors are truncated. |

#### .env file loading

The app loads environment variables from a `.env` file at startup. It searches for the first existing file in this order:

1. `.env` in the project root
2. `/etc/secrets/.env` (Render secret-file mount)
3. `envs/local.env` (local development convention)

**Precedence:** Process environment variables (e.g. from the Render dashboard) always override values from the file. This lets you override secrets or per-environment settings without editing the uploaded file.

**Render setup:** Create an environment group (e.g. `notion-pipeliner-backend`) and add a secret file with filename `.env`; its contents are mounted at `/etc/secrets/.env`. The app loads it automatically. Link the env group to both `notion-pipeliner-api` and `notion-pipeliner-worker`, or set variables in the Render dashboard; those take precedence over any file.

## API Reference

| Method | Path | Header | Response |
|--------|------|--------|----------|
| GET | `/` | `Authorization: <secret>` | 200 — `{"message": "Hello there!"}` |
| GET | `/` | (missing or invalid) | 401 — Unauthorized |
| POST | `/locations` | `Authorization: <secret>`, body `{keywords: "..."}` | 200 — When async enabled: `{status: "accepted", job_id: "loc_..."}`; when sync: Notion page |
| POST | `/locations` | `Authorization: <secret>`, body `{keywords: ""}` | 400 — keywords required and non-empty |
| GET | `/test/googlePlacesSearch?query=<QUERY>` | `Authorization: <secret>` | 200 — `{"query": "...", "results": [...]}` |
| GET | `/test/claude?poem_seed=<SEED>` | `Authorization: <secret>` | 200 — `{"poem": "..."}` |

## Project Structure

```
app/
  main.py
  models/schema.py           # DatabaseSchema, PropertySchema, SelectOption
  services/
    notion_service.py        # NotionService (delegates to SchemaCache)
    schema_cache.py          # TTL-based schema cache
    claude_service.py
    google_places_service.py
    location_service.py
    communicator.py          # Run-status notification orchestration
    whatsapp_service.py      # Twilio WhatsApp transport
  pipeline_lib/              # Pipeline framework
    core.py, context.py, orchestration.py, logging.py, default.py
    stage_pipelines/, steps/
  app_global_pipelines/     # PlacesGlobalPipeline
  custom_pipelines/          # Per-property pipelines (title, type, etc.)
  routes/
  queue/                    # Async job queue, worker loop, event bus (durable via Supabase pgmq when configured)
supabase/
  config.toml               # Supabase CLI config (ports, auth, etc.)
  migrations/               # Versioned SQL migrations (schema changes via PR only)
docs/
  architecture-design.md
  pipeline-framework.md      # Framework reference
http-test/
tests/
requirements.txt
render.yaml
pytest.ini
Makefile
README.md
```
