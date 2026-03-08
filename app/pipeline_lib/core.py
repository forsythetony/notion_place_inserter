"""Core pipeline abstractions: GlobalPipeline, Stage, Pipeline, PipelineStep."""

from abc import ABC, abstractmethod
from typing import Any

from app.pipeline_lib.context import PipelineRunContext


class PipelineStep(ABC):
    """Ordered operation inside a pipeline. Steps run sequentially."""

    @property
    @abstractmethod
    def step_id(self) -> str:
        """Unique identifier for this step."""
        ...

    @property
    def name(self) -> str:
        """Human-readable name for logging. Defaults to step_id."""
        return self.step_id

    @property
    def description(self) -> str:
        """Optional description for logging. Defaults to class docstring or empty."""
        doc = (type(self).__doc__ or "").strip()
        return doc.split("\n")[0] if doc else ""

    @abstractmethod
    def execute(
        self, context: PipelineRunContext, current_value: Any
    ) -> Any:
        """
        Execute the step. Receives context and current_value from previous step.
        Returns the transformed value for the next step.
        """
        ...


class Pipeline(ABC):
    """Work unit inside a stage. Contains ordered steps that run sequentially."""

    @property
    @abstractmethod
    def pipeline_id(self) -> str:
        """Unique identifier for this pipeline."""
        ...

    @property
    def name(self) -> str:
        """Human-readable name for logging. Defaults to pipeline_id."""
        return self.pipeline_id

    @property
    def description(self) -> str:
        """Optional description for logging. Defaults to class docstring or empty."""
        doc = (type(self).__doc__ or "").strip()
        return doc.split("\n")[0] if doc else ""

    @abstractmethod
    def steps(self) -> list[PipelineStep]:
        """Ordered list of steps to execute."""
        ...

    def run(self, context: PipelineRunContext) -> Any | None:
        """
        Execute all steps in order. Steps pass value through.
        Returns the final value from the last step (for property pipelines).
        """
        current_value: Any = None
        for step in self.steps():
            current_value = step.execute(context, current_value)
        return current_value


class Stage(ABC):
    """
    Dependency boundary between sets of work.
    Stages run sequentially by default; parallel mode fans out pipelines and joins.
    """

    @property
    @abstractmethod
    def stage_id(self) -> str:
        """Unique identifier for this stage."""
        ...

    @property
    def name(self) -> str:
        """Human-readable name for logging. Defaults to stage_id."""
        return self.stage_id

    @property
    def description(self) -> str:
        """Optional description for logging. Defaults to class docstring or empty."""
        doc = (type(self).__doc__ or "").strip()
        return doc.split("\n")[0] if doc else ""

    @property
    def run_mode(self) -> str:
        """'sequential' or 'parallel'. Default: sequential."""
        return "sequential"

    def pipelines(self, context: PipelineRunContext | None = None) -> list[Pipeline]:
        """Pipelines to run. In parallel mode, these run concurrently. Context optional for stages that need it."""
        return self._pipelines_impl(context)

    @abstractmethod
    def _pipelines_impl(self, context: PipelineRunContext | None) -> list[Pipeline]:
        """Override to return pipelines. Context is set when stage runs (after prior stages)."""
        ...

    def run(self, context: PipelineRunContext) -> None:
        """Execute pipelines. Delegates to orchestration for sequential/parallel."""
        from app.pipeline_lib.orchestration import run_stage

        run_stage(self, context)


class GlobalPipeline(ABC):
    """
    Top-level orchestrator scoped to one database schema.
    Runs stages in declared order.
    """

    @property
    @abstractmethod
    def pipeline_id(self) -> str:
        """Unique identifier for this global pipeline."""
        ...

    @property
    def name(self) -> str:
        """Human-readable name for logging. Defaults to pipeline_id."""
        return self.pipeline_id

    @property
    def description(self) -> str:
        """Optional description for logging. Defaults to class docstring or empty."""
        doc = (type(self).__doc__ or "").strip()
        return doc.split("\n")[0] if doc else ""

    @property
    @abstractmethod
    def schema_binding(self) -> str:
        """Notion database name this pipeline is bound to."""
        ...

    @abstractmethod
    def stages(self) -> list[Stage]:
        """Ordered list of stages to run."""
        ...

    def run(self, context: PipelineRunContext) -> None:
        """Execute all stages in order."""
        from app.pipeline_lib.orchestration import run_global_pipeline

        run_global_pipeline(self, context)
