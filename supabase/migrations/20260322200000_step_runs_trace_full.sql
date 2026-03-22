-- Full per-step trace for admin Monitoring (inputs, bindings, config, outputs; JSON-safe, not truncated).
ALTER TABLE step_runs ADD COLUMN IF NOT EXISTS step_trace_full jsonb;
