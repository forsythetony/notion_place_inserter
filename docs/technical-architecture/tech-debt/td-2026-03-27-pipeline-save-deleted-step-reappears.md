# Tech Debt: Deleted pipeline step reappears after Save

## ID

- `td-2026-03-27-pipeline-save-deleted-step-reappears`

## Status

- **Fixed in repo** — `PostgresJobRepository.save_job_graph` deletes step rows for each pipeline that are not present in the saved graph (after upserts). See `app/repositories/postgres_repositories.py`.

## Where

- **Backend:** `app/repositories/postgres_repositories.py` — `save_job_graph`, `get_graph_by_id`
- **API:** `PUT /management/pipelines/{pipeline_id}` — returns `job_graph_to_yaml_dict(saved)` after save
- **UI:** `notion_pipeliner_ui` — editor calls `flowToGraph` then `saveManagementPipeline`; `setPayload(saved)` reflects the API response

## Observed behavior

- User removes a step on the pipeline canvas and clicks **Save**.
- The step comes back (often immediately after save completes), as if the delete never persisted.

## Steps to reproduce (before fix)

1. Open a pipeline with at least one step in the Postgres-backed environment.
2. Delete a step (so it disappears from the canvas and local payload sync).
3. Click **Save**.
4. The step reappears in the graph (from the saved response / reload).

## Expected behavior

- Saved pipeline matches the graph the user saved; removed steps stay removed.

## Why this existed

- **Proven:** `save_job_graph` **upserted** job, stages, pipelines, and steps but **never deleted** rows that were no longer in the submitted graph.
- `get_graph_by_id` loads steps with `WHERE pipeline_id = …`, so any orphan `step_instances` rows were still returned and serialized back to the client.

The editor was sending a graph without the step; the API saved upserts but left the old step row in `step_instances`, and the response reloaded it.

## Goal

- Persisted graph matches the PUT body for steps: no orphan step rows for a pipeline after save.

## Suggested follow-ups

1. **Stages / pipelines:** The same upsert-only pattern may leave orphan `stage_definitions` or `pipeline_definitions` rows if the product ever allows removing entire stages or pipelines from the editor. Track separately if that ships.
2. **YAML / non-Postgres job repo:** Confirm whether `YamlJobRepository.save_job_graph` rewrites the full file (true replace) so the same class of bug does not apply there.

## Evidence (optional)

- Compare **request** body of `PUT /management/pipelines/{id}` (step absent) with **response** (step present) before the fix; network tab is enough—no server logs required.
