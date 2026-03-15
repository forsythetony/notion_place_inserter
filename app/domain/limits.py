"""Application limits for abuse prevention in Phase 3 domain model."""

from dataclasses import dataclass


@dataclass
class AppLimits:
    """Globally readable limits for validation and execution guardrails.

    These values are currently loaded from tenant app_config (YAML) or defaults.
    In the future they will be pulled from backend configuration (e.g. env, DB,
    or admin settings) so they can be configured easily and passed to the
    frontend to display to users while configuring jobs, stages, and pipelines.
    """

    max_stages_per_job: int
    max_pipelines_per_stage: int
    max_steps_per_pipeline: int
