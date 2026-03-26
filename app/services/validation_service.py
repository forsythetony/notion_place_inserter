"""Definition validation service for Phase 3 product model. Enforces integrity at save time."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.services.trigger_binding_migration import (
    legacy_raw_input_replacement_signal_ref,
    migrate_raw_input_signal_refs_for_steps,
)

if TYPE_CHECKING:
    from app.domain.connectors import ConnectorInstance, ConnectorTemplate
    from app.domain.jobs import (
        JobDefinition,
        PipelineDefinition,
        StageDefinition,
        StepInstance,
        StepTemplate,
    )
    from app.domain.limits import AppLimits
    from app.domain.repositories import (
        AppConfigRepository,
        ConnectorInstanceRepository,
        ConnectorTemplateRepository,
        StepTemplateRepository,
        TargetRepository,
        TargetSchemaRepository,
        TargetTemplateRepository,
        TriggerJobLinkRepository,
        TriggerRepository,
    )
    from app.domain.targets import (
        DataTarget,
        TargetSchemaProperty,
        TargetSchemaSnapshot,
        TargetTemplate,
    )
    from app.domain.triggers import TriggerDefinition


# Terminal step kinds: pipeline must end with one of these
_TERMINAL_STEP_KINDS = frozenset({"cache_set", "property_set"})


class ValidationError(ValueError):
    """Raised when definition validation fails. Supports single or aggregated errors."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        self.errors = errors or [message]
        combined = "; ".join(self.errors) if len(self.errors) > 1 else self.errors[0]
        super().__init__(combined)


@dataclass
class JobGraph:
    """Full job definition graph for validation: job + stages + pipelines + steps."""

    job: "JobDefinition"
    stages: list["StageDefinition"]
    pipelines: list["PipelineDefinition"]
    steps: list["StepInstance"]


class ValidationService:
    """
    Validates product model definitions at save time.
    Enforces ID resolution, sequencing, limits, terminal-step rules, and binding resolution.
    """

    def __init__(
        self,
        *,
        trigger_repo: "TriggerRepository | None" = None,
        trigger_job_link_repo: "TriggerJobLinkRepository | None" = None,
        target_repo: "TargetRepository | None" = None,
        target_schema_repo: "TargetSchemaRepository | None" = None,
        target_template_repo: "TargetTemplateRepository | None" = None,
        step_template_repo: "StepTemplateRepository | None" = None,
        connector_template_repo: "ConnectorTemplateRepository | None" = None,
        connector_instance_repo: "ConnectorInstanceRepository | None" = None,
        app_config_repo: "AppConfigRepository | None" = None,
    ) -> None:
        self._trigger_repo = trigger_repo
        self._trigger_job_link_repo = trigger_job_link_repo
        self._target_repo = target_repo
        self._target_schema_repo = target_schema_repo
        self._target_template_repo = target_template_repo
        self._step_template_repo = step_template_repo
        self._connector_template_repo = connector_template_repo
        self._connector_instance_repo = connector_instance_repo
        self._app_config_repo = app_config_repo

    async def _maybe_migrate_legacy_trigger_bindings(self, graph: JobGraph) -> None:
        """Rewrite legacy raw_input trigger refs when all linked triggers declare keywords."""
        if not self._trigger_repo or not self._trigger_job_link_repo:
            return
        try:
            trigger_ids = await self._trigger_job_link_repo.list_trigger_ids_for_job(
                graph.job.id, graph.job.owner_user_id
            )
        except Exception:
            return
        if not trigger_ids:
            return
        owner = graph.job.owner_user_id
        trigger_defs = []
        for tid in trigger_ids:
            trig = await self._trigger_repo.get_by_id(tid, owner)
            if trig is None:
                return
            trigger_defs.append(trig)
        replacement = legacy_raw_input_replacement_signal_ref(trigger_defs)
        if not replacement:
            return
        n = migrate_raw_input_signal_refs_for_steps(graph.steps, replacement)
        if n:
            logger.info(
                "trigger_bindings_migrated_raw_input_to_keywords | job_id={} bindings_updated={}",
                graph.job.id,
                n,
            )

    async def validate_job_graph(
        self,
        graph: JobGraph,
        *,
        skip_reference_checks: bool = False,
    ) -> None:
        """
        Validate a full job graph. Raises ValidationError on failure.
        Set skip_reference_checks=True when referenced entities may not yet be persisted.
        """
        await self._maybe_migrate_legacy_trigger_bindings(graph)
        errors: list[str] = []
        job = graph.job
        stages = graph.stages
        pipelines = graph.pipelines
        steps = graph.steps

        # Job must have at least one stage
        if not job.stage_ids:
            errors.append("job must have at least one stage")
        else:
            # Stage IDs in job must match provided stages
            stage_ids = {s.id for s in stages}
            for sid in job.stage_ids:
                if sid not in stage_ids:
                    errors.append(f"stage '{sid}' referenced in job not found in graph")

        # Build lookup maps
        stages_by_id = {s.id: s for s in stages}
        pipelines_by_id = {p.id: p for p in pipelines}
        steps_by_pipeline: dict[str, list[StepInstance]] = {}
        for s in steps:
            steps_by_pipeline.setdefault(s.pipeline_id, []).append(s)

        # Stage-level checks
        for stage in stages:
            if not stage.pipeline_ids:
                errors.append(f"stage '{stage.id}' must have at least one pipeline")
            for pid in stage.pipeline_ids:
                if pid not in pipelines_by_id:
                    errors.append(f"pipeline '{pid}' referenced in stage '{stage.id}' not found")
                else:
                    pipe = pipelines_by_id[pid]
                    if pipe.stage_id != stage.id:
                        errors.append(
                            f"pipeline '{pid}' has stage_id '{pipe.stage_id}' but is in stage '{stage.id}'"
                        )

        # Pipeline-level checks
        for pipeline in pipelines:
            pipe_steps = steps_by_pipeline.get(pipeline.id, [])
            if not pipe_steps:
                errors.append(f"pipeline '{pipeline.id}' must have at least one step")
            for step in pipe_steps:
                if step.pipeline_id != pipeline.id:
                    errors.append(
                        f"step '{step.id}' has pipeline_id '{step.pipeline_id}' but is in pipeline '{pipeline.id}'"
                    )

        # Sequence uniqueness
        stage_seqs = [s.sequence for s in stages]
        if len(stage_seqs) != len(set(stage_seqs)):
            errors.append("stage sequences must be unique within job")
        for stage in stages:
            pipes_in_stage = [p for p in pipelines if p.stage_id == stage.id]
            pipe_seqs = [p.sequence for p in pipes_in_stage]
            if len(pipe_seqs) != len(set(pipe_seqs)):
                errors.append(f"pipeline sequences must be unique within stage '{stage.id}'")
        for pipeline in pipelines:
            pipe_steps = sorted(steps_by_pipeline.get(pipeline.id, []), key=lambda s: s.sequence)
            step_seqs = [s.sequence for s in pipe_steps]
            if len(step_seqs) != len(set(step_seqs)):
                errors.append(f"step sequences must be unique within pipeline '{pipeline.id}'")

        # Terminal step rule: each pipeline must end with cache_set or property_set
        if self._step_template_repo:
            for pipeline in pipelines:
                pipe_steps = sorted(
                    steps_by_pipeline.get(pipeline.id, []),
                    key=lambda s: s.sequence,
                )
                if not pipe_steps:
                    continue
                last_step = pipe_steps[-1]
                template = await self._step_template_repo.get_by_id(last_step.step_template_id)
                if template is None:
                    errors.append(
                        f"step '{last_step.id}' references unknown step_template_id '{last_step.step_template_id}'"
                    )
                elif template.step_kind not in _TERMINAL_STEP_KINDS:
                    errors.append(
                        f"pipeline '{pipeline.id}' must terminate with Cache Set or Property Set; "
                        f"last step '{last_step.id}' has kind '{template.step_kind}'"
                    )
                elif template.step_kind == "property_set":
                    target_kind = last_step.config.get("target_kind", "schema_property")
                    # data_target_id is job-level; steps inherit job.target_id. If present (legacy), must match.
                    data_target_id = last_step.config.get("data_target_id")
                    if data_target_id and data_target_id != job.target_id:
                        errors.append(
                            f"Property Set step '{last_step.id}' config.data_target_id '{data_target_id}' "
                            f"does not match job target '{job.target_id}'"
                        )
                    elif target_kind == "page_metadata":
                        target_field = last_step.config.get("target_field")
                        if not target_field:
                            errors.append(
                                f"Property Set step '{last_step.id}' with target_kind=page_metadata "
                                "must have config.target_field"
                            )
                        elif target_field not in ("cover_image", "icon_image"):
                            errors.append(
                                f"Property Set step '{last_step.id}' target_field '{target_field}' "
                                "must be cover_image or icon_image"
                            )
                    else:
                        # schema_property mode: require schema_property_id and validate against target
                        schema_property_id = last_step.config.get("schema_property_id")
                        if not schema_property_id:
                            errors.append(
                                f"Property Set step '{last_step.id}' must have config.schema_property_id "
                                "(or use target_kind=page_metadata with target_field)"
                            )
                        elif self._target_schema_repo and not skip_reference_checks:
                            schema = await self._target_schema_repo.get_active_for_target(
                                job.target_id, job.owner_user_id
                            )
                            if schema is None:
                                errors.append(
                                    f"no active schema for job target '{job.target_id}'"
                                )
                            else:
                                prop_ids = {p.id for p in schema.properties}
                                if schema_property_id not in prop_ids:
                                    errors.append(
                                        f"Property Set step '{last_step.id}' references schema_property_id "
                                        f"'{schema_property_id}' not found in target schema"
                                    )

        # Step input bindings resolution (signal_ref: same pipeline only; cross-pipeline via cache_key_ref)
        if self._step_template_repo:
            for step in steps:
                await self._validate_step_bindings(step, steps, job, errors)

        # Limits (from AppConfigRepository; will be backend-configurable for frontend display)
        limits = (
            await self._app_config_repo.get_by_owner(job.owner_user_id)
            if self._app_config_repo
            else None
        )
        if limits:
            if len(stages) > limits.max_stages_per_job:
                errors.append(
                    f"job exceeds max_stages_per_job ({limits.max_stages_per_job}): has {len(stages)}"
                )
            for stage in stages:
                pipes_in_stage = [p for p in pipelines if p.stage_id == stage.id]
                if len(pipes_in_stage) > limits.max_pipelines_per_stage:
                    errors.append(
                        f"stage '{stage.id}' exceeds max_pipelines_per_stage "
                        f"({limits.max_pipelines_per_stage}): has {len(pipes_in_stage)}"
                    )
            for pipeline in pipelines:
                pipe_steps = steps_by_pipeline.get(pipeline.id, [])
                if len(pipe_steps) > limits.max_steps_per_pipeline:
                    errors.append(
                        f"pipeline '{pipeline.id}' exceeds max_steps_per_pipeline "
                        f"({limits.max_steps_per_pipeline}): has {len(pipe_steps)}"
                    )

        # Reference checks (target) - skip when entities not yet persisted
        # Trigger-job linkage is many-to-many via trigger_job_links; validated at link time
        if not skip_reference_checks:
            if self._target_repo:
                target = await self._target_repo.get_by_id(job.target_id, job.owner_user_id)
                if target is None:
                    errors.append(f"target_id '{job.target_id}' not found for owner")

        if errors:
            raise ValidationError("validation failed", errors)

    def _step_ids_in_execution_order(
        self,
        stages: list["StageDefinition"],
        pipelines: list["PipelineDefinition"],
        steps: list["StepInstance"],
    ) -> list[str]:
        """Return step IDs in execution order (stage order, pipeline order, step order)."""
        result: list[str] = []
        stages_sorted = sorted(stages, key=lambda s: s.sequence)
        pipelines_by_stage: dict[str, list[PipelineDefinition]] = {}
        for p in pipelines:
            pipelines_by_stage.setdefault(p.stage_id, []).append(p)
        for stage in stages_sorted:
            pipes = sorted(pipelines_by_stage.get(stage.id, []), key=lambda p: p.sequence)
            for pipe in pipes:
                pipe_steps = sorted(
                    [s for s in steps if s.pipeline_id == pipe.id],
                    key=lambda s: s.sequence,
                )
                for s in pipe_steps:
                    result.append(s.id)
        return result

    async def _validate_step_bindings(
        self,
        step: "StepInstance",
        all_steps: list["StepInstance"],
        job: "JobDefinition",
        errors: list[str],
    ) -> None:
        """Validate that step input bindings resolve to known sources.

        signal_ref to step.* is allowed only within the same pipeline (preceding steps).
        Cross-pipeline / cross-stage data must use cache_key_ref.
        """
        pipe_steps = sorted(
            [s for s in all_steps if s.pipeline_id == step.pipeline_id],
            key=lambda s: s.sequence,
        )
        pipe_step_ids = [s.id for s in pipe_steps]

        for _field, binding in step.input_bindings.items():
            if not isinstance(binding, dict):
                continue
            if "signal_ref" in binding:
                ref = binding["signal_ref"]
                if not isinstance(ref, str):
                    errors.append(f"step '{step.id}' signal_ref must be string")
                    continue
                if ref.startswith("trigger."):
                    continue  # trigger is always valid
                if ref.startswith("step."):
                    # step.step_<id>.<field>
                    parts = ref.split(".", 2)
                    if len(parts) < 3:
                        errors.append(f"step '{step.id}' invalid signal_ref format: {ref}")
                        continue
                    ref_step_id = parts[1]
                    if ref_step_id not in pipe_step_ids:
                        errors.append(
                            f"step '{step.id}' signal_ref '{ref}' references step '{ref_step_id}' "
                            "not in the same pipeline (use cache_set + cache_key_ref for cross-pipeline data)"
                        )
                        continue
                    idx = pipe_step_ids.index(step.id)
                    ref_idx = pipe_step_ids.index(ref_step_id)
                    if ref_idx >= idx:
                        errors.append(
                            f"step '{step.id}' signal_ref '{ref}' references step that does not precede it"
                        )
                    continue
                errors.append(f"step '{step.id}' signal_ref '{ref}' has unknown format")
            if "cache_key" in binding:
                continue  # cache key is valid
            if "cache_key_ref" in binding:
                continue  # resolved at runtime against run cache
        # Check config for target_schema_ref (e.g. in ai_constrain_values)
        for key, val in step.config.items():
            if key == "allowable_values_source" and isinstance(val, dict):
                tsr = val.get("target_schema_ref")
                if isinstance(tsr, dict):
                    tid = tsr.get("data_target_id")
                    pid = tsr.get("schema_property_id")
                    if pid:
                        # data_target_id is job-level; if present (legacy), must match job target
                        effective_tid = tid or job.target_id
                        if tid and tid != job.target_id:
                            errors.append(
                                f"step '{step.id}' target_schema_ref data_target_id '{tid}' "
                                f"does not match job target '{job.target_id}'"
                            )
                        elif self._target_schema_repo:
                            schema = await self._target_schema_repo.get_active_for_target(
                                effective_tid, job.owner_user_id
                            )
                            if schema and pid not in {p.id for p in schema.properties}:
                                errors.append(
                                    f"step '{step.id}' target_schema_ref schema_property_id '{pid}' "
                                    f"not found in target schema"
                                )

    def validate_stage_definition(self, stage: "StageDefinition") -> None:
        """Validate a stage definition. Raises ValidationError on failure."""
        errors: list[str] = []
        if not stage.pipeline_ids:
            errors.append(f"stage '{stage.id}' must have at least one pipeline")
        if errors:
            raise ValidationError("stage validation failed", errors)

    def validate_pipeline_definition(self, pipeline: "PipelineDefinition") -> None:
        """Validate a pipeline definition (structure only). Raises ValidationError on failure."""
        errors: list[str] = []
        if not pipeline.step_ids:
            errors.append(f"pipeline '{pipeline.id}' must have at least one step")
        if errors:
            raise ValidationError("pipeline validation failed", errors)

    async def validate_step_instance(
        self,
        step: "StepInstance",
        step_template: "StepTemplate | None" = None,
    ) -> None:
        """
        Validate a step instance (structure only).
        Full binding resolution requires validate_job_graph.
        """
        errors: list[str] = []
        if not step.step_template_id:
            errors.append(f"step '{step.id}' must have step_template_id")
        if step_template is None and self._step_template_repo:
            step_template = await self._step_template_repo.get_by_id(step.step_template_id)
        if step_template is None and step.step_template_id:
            errors.append(
                f"step '{step.id}' references unknown step_template_id '{step.step_template_id}'"
            )
        if errors:
            raise ValidationError("step instance validation failed", errors)

    async def validate_trigger(self, trigger: "TriggerDefinition") -> None:
        """Validate a trigger definition. Raises ValidationError on failure."""
        errors: list[str] = []
        if not trigger.path or not trigger.path.strip():
            errors.append("trigger path is required")
        # job_id may be None for triggers created before pipeline assignment
        if self._trigger_repo:
            existing = await self._trigger_repo.get_by_path(trigger.path, trigger.owner_user_id)
            if existing is not None and existing.id != trigger.id:
                errors.append(f"trigger path '{trigger.path}' already in use by another trigger for owner")
        if errors:
            raise ValidationError("trigger validation failed", errors)

    async def validate_data_target(self, target: "DataTarget") -> None:
        """Validate a data target. Raises ValidationError on failure."""
        errors: list[str] = []
        if not target.target_template_id:
            errors.append("target_template_id is required")
        if not target.connector_instance_id:
            errors.append("connector_instance_id is required")
        if self._target_template_repo:
            tmpl = await self._target_template_repo.get_by_id(target.target_template_id)
            if tmpl is None:
                errors.append(f"target_template_id '{target.target_template_id}' not found")
        if self._connector_instance_repo:
            inst = await self._connector_instance_repo.get_by_id(
                target.connector_instance_id, target.owner_user_id
            )
            if inst is None:
                errors.append(
                    f"connector_instance_id '{target.connector_instance_id}' not found for owner"
                )
        if errors:
            raise ValidationError("data target validation failed", errors)
