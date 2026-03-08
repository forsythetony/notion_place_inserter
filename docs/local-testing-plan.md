# Local Testing Plan

Step-by-step guide for testing the Notion Place Inserter application locally.

## Prerequisites

1. **Python 3.11+** with virtual environment
2. **Environment configured** — copy `envs/env.template` to `envs/local.env` and fill in:
   - `NOTION_API_KEY` — from [Notion integrations](https://www.notion.so/my-integrations)
   - `ANTHROPIC_TOKEN` — Anthropic API key
   - `GOOGLE_PLACES_API_KEY` — from [Google Cloud Console](https://console.cloud.google.com/) (Places API enabled)
   - `BASE_URL` — `http://localhost:8000` for local
   - `SECRET` — `dev-secret` or your chosen auth value
   - `DRY_RUN` — (optional) set to `1` to echo property payloads without creating Notion pages

## Phase 1: Setup and Smoke Tests

| Step | Command | Expected |
|------|---------|----------|
| 1. Install deps | `make install` | Dependencies install without error |
| 2. Start server | `make run` | Server starts on port 8000 |
| 3. Auth check (no header) | `curl http://localhost:8000/` | 401 Unauthorized |
| 4. Auth check (valid) | `curl -H "Authorization: dev-secret" http://localhost:8000/` | 200, `{"message": "Hello there!"}` |
| 5. Quick Makefile test | `make test` | Prints status and body for both auth checks (expect 401 then 200) |

## Phase 2: Unit Tests (No Server Required)

| Step | Command | Expected |
|------|---------|----------|
| 1. Schema cache tests | `python -m pytest tests/test_schema_cache.py -v` | 3 tests pass (parse_schema, TTL refresh, invalidate) |

## Phase 3: API Tests (Server Must Be Running)

Start the server in one terminal (`make run`), then in another:

| Step | Command | Expected |
|------|---------|----------|
| 1. Full API suite | `make test-api` | 11 tests pass (8 Tavern + 3 unit) |
| 2. Tavern only | `set -a && source envs/local.env && set +a && python -m pytest http-test/ -v` | 8 Tavern tests pass |

**Note:** `make test-api` sources `envs/local.env` automatically. Tavern needs `BASE_URL` and `SECRET` in the environment.

## Phase 4: Manual Endpoint Verification

With server running:

| Endpoint | Command | Expected |
|----------|---------|----------|
| Google Places search | `make test-google-places` or `curl -H "Authorization: dev-secret" "http://localhost:8000/test/googlePlacesSearch?query=pizza+new+york"` | 200, JSON with `query` and `results` |
| Claude poem | `curl -H "Authorization: dev-secret" "http://localhost:8000/test/claude?poem_seed=sunset"` | 200, JSON with `poem` |
| Random location (test) | `make test-random-location` or `curl -X POST -H "Authorization: dev-secret" http://localhost:8000/test/randomLocation` | 200, Notion page object (random entry) |
| Locations (pipeline) | `curl -X POST -H "Authorization: dev-secret" -H "Content-Type: application/json" -d '{"keywords":"stone arch bridge minneapolis"}' http://localhost:8000/locations` | 200, Notion page object (pipeline-created) |

### Dry-Run Mode (Echo Only, No Notion Writes)

To validate property values without creating Notion pages, start the server with `DRY_RUN=1`:

```bash
make run-dry-run
```

Or add `DRY_RUN=1` to `envs/local.env` and run `make run`. Then call the same endpoints:

| Endpoint | Command | Expected |
|----------|---------|----------|
| Locations (dry-run) | `curl -X POST -H "Authorization: dev-secret" -H "Content-Type: application/json" -d '{"keywords":"stone arch bridge minneapolis"}' http://localhost:8000/locations` | 200, `{mode: "dry_run", database: "Places to Visit", properties: {...}, summary: {property_count, property_names}, keywords: "..."}` |
| Random location (dry-run) | `curl -X POST -H "Authorization: dev-secret" http://localhost:8000/test/randomLocation` | 200, same structure (no `keywords` field) |

No Notion page is created; the response echoes the computed properties for manual inspection. The server console prints a rich table (Property, Type, Value) for each request to help parse property resolution during local debugging.

## Phase 5: Integration Test (Optional)

For end-to-end pipeline validation against a live server:

| Step | Command | Expected |
|------|---------|----------|
| 1. Run integration | `RUN_INTEGRATION=1 python -m pytest tests/test_locations_integration.py -v` | 2 tests pass (POST /locations, POST /test/randomLocation) |

## Phase 6: Schema Cache and Pipeline Behavior

| Test | How to verify |
|------|---------------|
| **TTL refresh** | Add a new property or select option in Notion. Wait 5+ minutes (or restart with shorter TTL for faster test). Create a location via pipeline — new property should appear in resolution. |
| **Parallel property stage** | Check logs when creating a location — look for `stage_fan_out_started` and `stage_completed` with `event=join_complete`. Property pipelines should log concurrently. |
| **Random entry (test)** | POST `/test/randomLocation` — creates random entry without calling Claude/Google. |
| **Location relation** | POST `/locations` with keywords like `"stone arch bridge minneapolis"` — in dry-run, check `properties.Location` for `{"relation": [{"id": "..."}]}`. |

## Troubleshooting

| Issue | Check |
|-------|-------|
| Tavern "MissingFormatError: BASE_URL" | Ensure `envs/local.env` exists and is sourced before pytest. Use `make test-api` which does this. |
| 500 on /locations | Check NOTION_API_KEY, ANTHROPIC_TOKEN, GOOGLE_PLACES_API_KEY in env. |
| Empty Google results | Verify Places API (New) is enabled and key has correct permissions. |
| Schema cache KeyError | Ensure Notion database IDs in `NotionService.DATABASE_IDS` match your workspace. |

## Quick Reference

```bash
# One-liner: install, run server (background), run tests
make install && make run &
sleep 5 && make test-api
```
