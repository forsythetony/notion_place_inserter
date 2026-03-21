# Pipeline step logging (INPUT / PROCESSING / FINAL)

Every step run emits three structured blocks at **INFO** (worker/API):

1. **INPUT** — `pipeline_step | INPUT` plus `INPUT LOG:` with resolved binding values and `config` (strings truncated for large payloads).
2. **PROCESSING** — Optional lines from step handlers via `ExecutionContext.log_step_processing("...")` (`pipeline_step | PROCESSING`).
3. **FINAL** — `pipeline_step | FINAL` plus `FINAL LOG:` with output previews, `Status` (`succeeded` / `failed`), `Runtime_ms`, and `Error` on failure.

Orchestration in `JobExecutionService._run_step` wraps all handlers; timing covers handler execution only.

## Persistence (DB + API)

The same sanitized payloads used for logs are stored on **`step_runs`** (v1 JSON):

| Column | Contents |
|--------|-----------|
| `input_summary` | `build_step_input_summary`: `schema_version`, `meta` (orchestration ids), `resolved_inputs`, `config`, `input_bindings` (all passed through `sanitize_for_step_log`). |
| `processing_log` | JSON array of strings — each entry matches one `log_step_processing` / `StepPipelineLog.processing` message (in order). |
| `output_summary` | `build_step_output_summary`: `schema_version`, `outputs`, `status`, `runtime_ms`, `error` (truncated like FINAL logs). |

`JobExecutionService._run_step` upserts **`running`** with `input_summary` + `processing_log: []`, then **`succeeded`** / **`failed`** with full `processing_log` and `output_summary`.

Before persistence, summaries pass through **`json_safe_for_db`** (round-trip JSON with a `default` handler) so nested values like **datetime**, **UUID**, **tuple** (from sanitization), **set**, and **bytes** are PostgREST/jsonb-safe; otherwise the Supabase client could omit or reject `input_summary` / `output_summary` columns.

**GET** [`GET /management/runs/{run_id}`](../../../../app/routes/management.py) includes **`step_traces`**: an array of `{ id, step_id, step_template_id, pipeline_id?, status, started_at, completed_at, error_summary, input, processing, output }` for polling (e.g. editor live test). `PostgresRunRepository.list_step_runs_for_job_run` loads rows ordered by `created_at` and joins `pipeline_run_executions` for `pipeline_id`.

Migration: `supabase/migrations/20260320120000_step_runs_processing_log.sql`.

## Environment

| Variable | Effect |
|----------|--------|
| `PIPELINE_STEP_LOG_VERBOSE=1` | Longer string previews in INPUT/FINAL (see `is_pipeline_step_log_verbose()`). |
| `PIPELINE_TRACE_VERBOSE=1` | Extra **DEBUG** `pipeline_trace \| ...` lines (e.g. optimize-input schema detail); binding JSON on INPUT at DEBUG. Independent of step framing. |

## Code

- [`app/services/job_execution/step_pipeline_log.py`](../../../../app/services/job_execution/step_pipeline_log.py) — `emit_step_input`, `emit_step_final`, `StepPipelineLog.processing` / `processing_lines`, `build_step_input_summary`, `build_step_output_summary`, sanitization.
- [`app/services/job_execution/runtime_types.py`](../../../../app/services/job_execution/runtime_types.py) — `ExecutionContext.log_step_processing`.
- [`app/services/job_execution/job_execution_service.py`](../../../../app/services/job_execution/job_execution_service.py) — `_run_step` integration; persists traces on `StepRun`; preserves `started_at` when completing.
