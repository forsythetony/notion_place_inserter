"""Application limits for abuse prevention in Phase 3 domain model."""

from dataclasses import dataclass


@dataclass
class AppLimits:
    """Globally readable limits for validation and execution guardrails."""

    max_stages_per_job: int
    max_pipelines_per_stage: int
    max_steps_per_pipeline: int
