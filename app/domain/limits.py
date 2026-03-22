"""Application limits for abuse prevention in Phase 3 domain model."""

from dataclasses import dataclass


@dataclass
class AppLimits:
    """Globally readable limits for validation and execution guardrails.

    Values are resolved from global + per-user ``app_limits`` rows (``min(global, user_candidate)``)
    when using Postgres; YAML mode uses tenant file defaults.
    """

    max_stages_per_job: int
    max_pipelines_per_stage: int
    max_steps_per_pipeline: int
    max_jobs_per_owner: int = 50
    max_triggers_per_owner: int = 50
    max_runs_per_utc_day: int = 500
    max_runs_per_utc_month: int = 10000
