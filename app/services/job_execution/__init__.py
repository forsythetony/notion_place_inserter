"""Snapshot-driven job execution for Phase 3 (p3_pr06).

Lazy exports avoid import cycles: ``pipeline_live_test.scoped_snapshot`` imports
``runtime_types``, which must not eagerly load ``JobExecutionService`` (that
module imports scoped helpers for cache fixtures).
"""

from __future__ import annotations

__all__ = ["JobExecutionService", "StepRuntimeRegistry"]


def __getattr__(name: str):
    if name == "JobExecutionService":
        from app.services.job_execution.job_execution_service import JobExecutionService

        return JobExecutionService
    if name == "StepRuntimeRegistry":
        from app.services.job_execution.step_runtime_registry import StepRuntimeRegistry

        return StepRuntimeRegistry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
