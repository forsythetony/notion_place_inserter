# Starter job reprovision (Notion Place Inserter)

Bundled definitions live under `product_model/bootstrap/` (job: `jobs/notion_place_inserter.yaml`, trigger: `triggers/trigger_http_locations.yaml`). For each owner, Postgres stores **copies** provisioned at runtime — editing YAML on disk does **not** automatically rewrite existing rows.

## When to use

- You changed bootstrap YAML and want your **account** to match the repo without hand-editing the pipeline editor.
- Starter job validation or bindings drifted (e.g. invalid cross-pipeline `signal_ref`); reprovision resets `job_notion_place_inserter` and the `/locations` HTTP trigger from current YAML.

## What gets replaced (destructive)

- **Deleted:** HTTP trigger whose path is `/locations` (for your user).
- **Deleted:** Job `job_notion_place_inserter` and its stages/pipelines/steps.
- **Re-created:** Same IDs from bundled YAML; **new** trigger **secret** (rotate behavior).
- **Not deleted:** Connector instances (`connector_instance_*`), data targets (`target_places_to_visit`, `target_locations`), or catalog templates.

## Makefile (local, macOS)

Copy your **Supabase `access_token` only** (the JWT string, not the word `Bearer`) to the clipboard, then from the repo root:

```bash
make reprovision-starter
```

Uses `pbpaste`, strips optional leading `Bearer ` / `bearer `, and posts to `BASE_URL` (defaults to `http://localhost:8000`; override with `BASE_URL=https://…`). Sources `envs/local.env` when present so `BASE_URL` can match your API.

## API (recommended)

With a normal management Bearer token (same as the Pipelines UI):

```http
POST /management/bootstrap/reprovision-starter
Authorization: Bearer <supabase_access_token>
```

**200** — JSON includes `job_id`, `trigger_path`, and a short message. Call `GET /management/triggers` afterward to copy the new webhook URL and secret.

**503** — `ENABLE_BOOTSTRAP_PROVISIONING` is off.

**401** — missing/invalid auth.

Implementation: `PostgresBootstrapProvisioningService.reprovision_owner_starter_definitions` in `app/services/postgres_seed_service.py`.

## Manual alternative (no new endpoint)

1. Remove the **`/locations` trigger** row for your user (deleting only the job is **not** enough — `ensure_owner_starter_definitions` exits early while that trigger exists).
2. Remove job `job_notion_place_inserter` if it remains orphaned.
3. Invoke any path that calls `ensure_owner_starter_definitions` (e.g. `POST` to the locations trigger URL after provisioning prerequisites), or use the endpoint above.

## After reprovisioning

- **API + Worker** — restart if you changed Python; YAML-only edits on disk require a running API that loads the updated files.
- **Supabase** — no migration for YAML-only changes.
- **Clients** — update any hard-coded trigger secret or webhook URL; reprovision issues a new secret.
