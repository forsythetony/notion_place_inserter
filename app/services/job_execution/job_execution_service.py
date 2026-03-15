"""Snapshot-driven job execution orchestrator."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from loguru import logger

from app.services.job_execution.binding_resolver import resolve_input_bindings
from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_registry import StepRuntimeRegistry
from app.services.job_execution.target_write_adapter import build_notion_properties_payload


def _default_registry() -> StepRuntimeRegistry:
    """Build registry with all bootstrap step handlers."""
    from app.services.job_execution.handlers import (
        AiConstrainValuesClaudeHandler,
        CacheGetHandler,
        CacheSetHandler,
        GooglePlacesLookupHandler,
        OptimizeInputClaudeHandler,
        PropertySetHandler,
    )

    reg = StepRuntimeRegistry()
    reg.register("step_template_optimize_input_claude", OptimizeInputClaudeHandler)
    reg.register("step_template_google_places_lookup", GooglePlacesLookupHandler)
    reg.register("step_template_cache_set", CacheSetHandler)
    reg.register("step_template_cache_get", CacheGetHandler)
    reg.register("step_template_ai_constrain_values_claude", AiConstrainValuesClaudeHandler)
    reg.register("step_template_property_set", PropertySetHandler)
    return reg


class JobExecutionService:
    """
    Executes jobs from resolved definition snapshots.
    Stages sequential; pipelines in stage parallel; steps in pipeline sequential.
    """

    def __init__(
        self,
        *,
        step_registry: StepRuntimeRegistry | None = None,
        notion_service: Any = None,
        claude_service: Any = None,
        google_places_service: Any = None,
        dry_run: bool = False,
    ) -> None:
        self._registry = step_registry or _default_registry()
        self._notion = notion_service
        self._claude = claude_service
        self._google = google_places_service
        self._dry_run = dry_run

    def execute_snapshot_run(
        self,
        snapshot: dict[str, Any],
        run_id: str,
        job_id: str,
        trigger_payload: dict[str, Any],
        definition_snapshot_ref: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a job from a resolved snapshot. Returns result dict with id, page_id, etc.
        """
        job_data = snapshot.get("job") or {}
        target_data = snapshot.get("target") or {}
        active_schema = snapshot.get("active_schema") or {}
        data_source_id = target_data.get("external_target_id") or ""

        if not data_source_id:
            raise ValueError("Snapshot target missing external_target_id")

        ctx = ExecutionContext(
            run_id=run_id,
            job_id=job_id,
            definition_snapshot_ref=definition_snapshot_ref,
            trigger_payload=trigger_payload,
            dry_run=self._dry_run,
        )
        ctx._services["claude"] = self._claude
        ctx._services["google_places"] = self._google
        ctx._services["notion"] = self._notion

        stages = sorted(
            (s for s in (job_data.get("stages") or []) if isinstance(s, dict) and s.get("id")),
            key=lambda s: s.get("sequence", 0),
        )

        for stage in stages:
            stage_id = stage.get("id", "")
            pipelines_data = stage.get("pipelines") or []
            run_mode = stage.get("pipeline_run_mode", "parallel")

            if run_mode == "parallel":
                self._run_parallel_pipelines(pipelines_data, ctx, snapshot, stage_id)
            else:
                for p_data in sorted(pipelines_data, key=lambda p: p.get("sequence", 0)):
                    self._run_pipeline(p_data, ctx, snapshot, stage_id)

        # Build final Notion payload and write
        notion_props = build_notion_properties_payload(ctx.properties, active_schema)
        if self._dry_run:
            return {
                "mode": "dry_run",
                "database": target_data.get("display_name", ""),
                "properties": notion_props,
                "id": None,
                "page_id": None,
            }

        if not self._notion:
            raise RuntimeError("NotionService not configured for target write")

        result = self._notion.create_page(
            data_source_id=data_source_id,
            properties=notion_props,
            icon=ctx.icon,
            cover=ctx.cover,
        )
        return result or {}

    def _run_pipeline(
        self,
        pipeline_data: dict[str, Any],
        ctx: ExecutionContext,
        snapshot: dict[str, Any],
        stage_id: str,
    ) -> None:
        steps_data = pipeline_data.get("steps") or []
        for step_data in sorted(steps_data, key=lambda s: s.get("sequence", 0)):
            self._run_step(step_data, ctx, snapshot, stage_id, pipeline_data.get("id", ""))

    def _run_parallel_pipelines(
        self,
        pipelines_data: list[dict[str, Any]],
        ctx: ExecutionContext,
        snapshot: dict[str, Any],
        stage_id: str,
    ) -> None:
        errors: list[tuple[str, Exception]] = []
        with ThreadPoolExecutor(max_workers=len(pipelines_data)) as executor:
            futures = {
                executor.submit(
                    self._run_pipeline,
                    p,
                    ctx,
                    snapshot,
                    stage_id,
                ): p.get("id", "")
                for p in pipelines_data
            }
            for future in as_completed(futures):
                pipeline_id = futures[future]
                try:
                    future.result()
                except Exception as e:
                    errors.append((pipeline_id, e))
                    logger.warning(
                        "job_execution_pipeline_failed | run_id={} stage_id={} pipeline_id={} error={}",
                        ctx.run_id,
                        stage_id,
                        pipeline_id,
                        e,
                    )
        if errors:
            raise errors[0][1]

    def _run_step(
        self,
        step_data: dict[str, Any],
        ctx: ExecutionContext,
        snapshot: dict[str, Any],
        stage_id: str,
        pipeline_id: str,
    ) -> None:
        step_id = step_data.get("id", "")
        step_template_id = step_data.get("step_template_id", "")
        handler = self._registry.get(step_template_id)
        if not handler:
            raise ValueError(
                f"Unknown step_template_id: {step_template_id} (step_id={step_id})"
            )

        input_bindings = step_data.get("input_bindings") or {}
        config = step_data.get("config") or {}
        resolved_inputs = resolve_input_bindings(input_bindings, ctx, snapshot)

        logger.debug(
            "job_execution_step_start | run_id={} stage_id={} pipeline_id={} step_id={} template={}",
            ctx.run_id,
            stage_id,
            pipeline_id,
            step_id,
            step_template_id,
        )

        outputs = handler.execute(
            step_id=step_id,
            config=config,
            input_bindings=input_bindings,
            resolved_inputs=resolved_inputs,
            ctx=ctx,
            snapshot=snapshot,
        )

        for out_name, out_val in (outputs or {}).items():
            ctx.set_step_output(step_id, out_name, out_val)
