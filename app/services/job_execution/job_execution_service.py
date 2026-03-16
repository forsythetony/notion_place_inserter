"""Snapshot-driven job execution orchestrator."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

from app.domain.runs import PipelineRun, StageRun, StepRun
from app.services.job_execution.binding_resolver import resolve_input_bindings

if TYPE_CHECKING:
    from app.domain.repositories import RunRepository
from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_registry import StepRuntimeRegistry
from app.services.job_execution.target_write_adapter import build_notion_properties_payload


def _normalize_property_slug(name: str) -> str:
    """Normalize a display name to a stable slug fragment."""
    return (
        (name or "")
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def _default_registry() -> StepRuntimeRegistry:
    """Build registry with all bootstrap step handlers."""
    from app.services.job_execution.handlers import (
        AiConstrainValuesClaudeHandler,
        CacheGetHandler,
        CacheSetHandler,
        DataTransformHandler,
        GooglePlacesLookupHandler,
        OptimizeInputClaudeHandler,
        PropertySetHandler,
        SearchIconsHandler,
        TemplaterHandler,
        UploadImageToNotionHandler,
        AiSelectRelationHandler,
        AiPromptHandler,
    )

    reg = StepRuntimeRegistry()
    reg.register("step_template_optimize_input_claude", OptimizeInputClaudeHandler)
    reg.register("step_template_google_places_lookup", GooglePlacesLookupHandler)
    reg.register("step_template_cache_set", CacheSetHandler)
    reg.register("step_template_cache_get", CacheGetHandler)
    reg.register("step_template_ai_constrain_values_claude", AiConstrainValuesClaudeHandler)
    reg.register("step_template_property_set", PropertySetHandler)
    reg.register("step_template_data_transform", DataTransformHandler)
    reg.register("step_template_templater", TemplaterHandler)
    reg.register("step_template_search_icons", SearchIconsHandler)
    reg.register("step_template_upload_image_to_notion", UploadImageToNotionHandler)
    reg.register("step_template_ai_select_relation", AiSelectRelationHandler)
    reg.register("step_template_ai_prompt", AiPromptHandler)
    return reg


class JobExecutionService:
    """
    Executes jobs from resolved definition snapshots.
    Stages sequential; pipelines in stage parallel or sequential; steps in pipeline sequential.

    TEMPORARY MITIGATION (2026-03): The bootstrap job uses pipeline_run_mode=sequential
    to avoid Errno 11 (Resource temporarily unavailable) under connection contention.
    All threads share a single Supabase client; parallel pipelines cause socket/DB
    exhaustion. This is NOT the final architecture. See td-2026-03-15-resource-constraints-
    db-connections-threads. Revert stages to parallel once connection pooling, per-thread
    clients, or controlled parallelism is in place.
    """

    def __init__(
        self,
        *,
        step_registry: StepRuntimeRegistry | None = None,
        notion_service: Any = None,
        claude_service: Any = None,
        google_places_service: Any = None,
        freepik_service: Any = None,
        dry_run: bool = False,
        run_repository: RunRepository | None = None,
        get_notion_token_fn: Callable[[str], str | None] | None = None,
    ) -> None:
        self._registry = step_registry or _default_registry()
        self._notion = notion_service
        self._claude = claude_service
        self._google = google_places_service
        self._freepik = freepik_service
        self._dry_run = dry_run
        self._run_repo = run_repository
        self._get_notion_token = get_notion_token_fn

    def execute_snapshot_run(
        self,
        snapshot: dict[str, Any],
        run_id: str,
        job_id: str,
        trigger_payload: dict[str, Any],
        definition_snapshot_ref: str | None = None,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a job from a resolved snapshot. Returns result dict with id, page_id, etc.
        """
        job_data = snapshot.get("job") or {}
        target_data = snapshot.get("target") or {}
        active_schema = snapshot.get("active_schema") or {}
        active_schema = self._ensure_active_schema(
            active_schema=active_schema,
            target_data=target_data,
        )
        if active_schema:
            # Ensure runtime binding resolution (target_schema_ref) can use synthesized schema.
            snapshot["active_schema"] = active_schema
        data_source_id = target_data.get("external_target_id") or ""

        if not data_source_id:
            raise ValueError("Snapshot target missing external_target_id")

        ctx = ExecutionContext(
            run_id=run_id,
            job_id=job_id,
            definition_snapshot_ref=definition_snapshot_ref,
            trigger_payload=trigger_payload,
            dry_run=self._dry_run,
            owner_user_id=owner_user_id or "",
        )
        ctx._services["claude"] = self._claude
        ctx._services["google_places"] = self._google
        ctx._services["notion"] = self._notion
        ctx._services["freepik"] = getattr(self, "_freepik", None)
        ctx._services["get_notion_token"] = self._get_notion_token
        if self._run_repo and owner_user_id:
            from app.services.usage_accounting_service import UsageAccountingService

            ctx._services["usage_accounting"] = UsageAccountingService(self._run_repo)

        stages = sorted(
            (s for s in (job_data.get("stages") or []) if isinstance(s, dict) and s.get("id")),
            key=lambda s: s.get("sequence", 0),
        )

        for stage in stages:
            stage_id = stage.get("id", "")
            pipelines_data = stage.get("pipelines") or []
            # pipeline_run_mode: "parallel" uses ThreadPoolExecutor; "sequential" runs
            # pipelines one-by-one. Sequential is a TEMPORARY mitigation for Errno 11
            # under shared Supabase client contention. Revert to parallel after
            # td-2026-03-15-resource-constraints-db-connections-threads is resolved.
            run_mode = stage.get("pipeline_run_mode", "parallel")
            if run_mode == "sequential":
                logger.info(
                    "job_execution_stage_sequential | run_id={} stage_id={} pipeline_count={} "
                    "(temporary mitigation for connection contention; see td-2026-03-15)",
                    run_id,
                    stage_id,
                    len(pipelines_data),
                )
            stage_run_id = f"{run_id}_stage_{stage_id}"
            if self._run_repo and owner_user_id:
                self._persist_stage_run(
                    stage_run_id=stage_run_id,
                    job_run_id=run_id,
                    stage_id=stage_id,
                    owner_user_id=owner_user_id,
                    status="running",
                )
            try:
                if run_mode == "parallel":
                    self._run_parallel_pipelines(
                        pipelines_data, ctx, snapshot, stage_id, run_id, stage_run_id, owner_user_id
                    )
                else:
                    for p_data in sorted(pipelines_data, key=lambda p: p.get("sequence", 0)):
                        self._run_pipeline(
                            p_data, ctx, snapshot, stage_id, run_id, stage_run_id, owner_user_id
                        )
                if self._run_repo and owner_user_id:
                    self._persist_stage_run(
                        stage_run_id=stage_run_id,
                        job_run_id=run_id,
                        stage_id=stage_id,
                        owner_user_id=owner_user_id,
                        status="succeeded",
                        completed_at=datetime.now(timezone.utc),
                    )
            except Exception as e:
                if self._run_repo and owner_user_id:
                    self._persist_stage_run(
                        stage_run_id=stage_run_id,
                        job_run_id=run_id,
                        stage_id=stage_id,
                        owner_user_id=owner_user_id,
                        status="failed",
                        completed_at=datetime.now(timezone.utc),
                    )
                raise

        # Build final Notion payload and write.
        # Prefer OAuth token when available; otherwise use global NotionService.
        notion_props = build_notion_properties_payload(ctx.properties, active_schema)
        access_token: str | None = None
        if self._get_notion_token and owner_user_id:
            access_token = self._get_notion_token(owner_user_id)
        token_source = "oauth" if access_token else "global"
        try:
            if access_token:
                from app.services.notion_service import NotionService

                result = NotionService.create_page_with_token(
                    access_token=access_token,
                    data_source_id=data_source_id,
                    properties=notion_props,
                    icon=ctx.icon,
                    cover=ctx.cover,
                    dry_run=self._dry_run,
                )
            elif self._notion:
                result = self._notion.create_page(
                    data_source_id=data_source_id,
                    properties=notion_props,
                    icon=ctx.icon,
                    cover=ctx.cover,
                )
            else:
                raise RuntimeError("NotionService not configured for target write")
        except Exception as e:
            logger.exception(
                "job_execution_notion_create_failed | run_id={} job_id={} owner_user_id={} data_source_id={} "
                "token_source={} error={}",
                run_id,
                job_id,
                owner_user_id or "",
                data_source_id,
                token_source,
                str(e)[:500],
            )
            raise
        if self._run_repo and owner_user_id:
            try:
                from app.domain.runs import UsageRecord

                record = UsageRecord(
                    id=f"usage_{uuid.uuid4().hex[:12]}",
                    job_run_id=run_id,
                    usage_type="external_api_call",
                    provider="notion",
                    metric_name="create_page",
                    metric_value=1,
                    owner_user_id=owner_user_id,
                )
                self._run_repo.save_usage_record(record)
            except Exception as e:
                logger.exception(
                    "job_execution_save_usage_notion_create_failed | run_id={} error={}",
                    run_id,
                    e,
                )
        return result or {}

    def _ensure_active_schema(
        self,
        *,
        active_schema: dict[str, Any],
        target_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Return usable active schema. If missing, synthesize from live Notion schema.

        Runtime expects active_schema properties with stable IDs (e.g. prop_tags).
        """
        props = active_schema.get("properties") if isinstance(active_schema, dict) else None
        if isinstance(props, list) and props:
            return active_schema
        if not self._notion:
            return active_schema

        db_name = (target_data.get("display_name") or "").strip()
        if not db_name:
            return active_schema
        try:
            _, raw_props = self._notion.get_raw_schema_for_sync(db_name)
        except Exception as exc:
            logger.warning(
                "job_execution_schema_fallback_failed | database={} error={}",
                db_name,
                exc,
            )
            return active_schema

        synthesized_props: list[dict[str, Any]] = []
        for prop_name, raw in (raw_props or {}).items():
            if not isinstance(raw, dict):
                continue
            prop_type = raw.get("type", "rich_text")
            options = None
            if prop_type in ("select", "multi_select"):
                opts = raw.get(prop_type, {}).get("options", [])
                options = [
                    {
                        "id": o.get("id", ""),
                        "name": o.get("name", ""),
                        "color": o.get("color", ""),
                    }
                    for o in opts
                    if isinstance(o, dict)
                ]
            synthesized_props.append(
                {
                    "id": f"prop_{_normalize_property_slug(prop_name)}",
                    "external_property_id": raw.get("id", prop_name),
                    "name": prop_name,
                    "normalized_slug": _normalize_property_slug(prop_name),
                    "property_type": prop_type,
                    "options": options,
                }
            )

        if not synthesized_props:
            return active_schema

        logger.info(
            "job_execution_schema_fallback_synthesized | database={} property_count={}",
            db_name,
            len(synthesized_props),
        )
        return {"id": "runtime_synthesized", "properties": synthesized_props}

    def _persist_stage_run(
        self,
        *,
        stage_run_id: str,
        job_run_id: str,
        stage_id: str,
        owner_user_id: str,
        status: str,
        completed_at: datetime | None = None,
    ) -> None:
        if not self._run_repo:
            return
        try:
            run = StageRun(
                id=stage_run_id,
                job_run_id=job_run_id,
                stage_id=stage_id,
                status=status,
                owner_user_id=owner_user_id,
                started_at=datetime.now(timezone.utc) if status == "running" else None,
                completed_at=completed_at,
            )
            self._run_repo.save_stage_run(run)
        except Exception as e:
            logger.exception(
                "job_execution_save_stage_run_failed | stage_run_id={} job_run_id={} error={}",
                stage_run_id,
                job_run_id,
                e,
            )

    def _run_pipeline(
        self,
        pipeline_data: dict[str, Any],
        ctx: ExecutionContext,
        snapshot: dict[str, Any],
        stage_id: str,
        job_run_id: str,
        stage_run_id: str,
        owner_user_id: str | None,
    ) -> None:
        pipeline_id = pipeline_data.get("id", "")
        pipeline_run_id = f"{job_run_id}_pipeline_{pipeline_id}"
        if self._run_repo and owner_user_id:
            try:
                self._run_repo.save_pipeline_run(
                    PipelineRun(
                        id=pipeline_run_id,
                        stage_run_id=stage_run_id,
                        pipeline_id=pipeline_id,
                        status="running",
                        owner_user_id=owner_user_id,
                        job_run_id=job_run_id,
                        started_at=datetime.now(timezone.utc),
                    )
                )
            except Exception as e:
                logger.exception(
                    "job_execution_save_pipeline_run_failed | pipeline_run_id={} error={}",
                    pipeline_run_id,
                    e,
                )
                # Must not proceed: step_runs FK requires pipeline_run_executions row to exist
                raise
        steps_data = pipeline_data.get("steps") or []
        try:
            for step_data in sorted(steps_data, key=lambda s: s.get("sequence", 0)):
                self._run_step(
                    step_data,
                    ctx,
                    snapshot,
                    stage_id,
                    pipeline_id,
                    job_run_id,
                    stage_run_id,
                    pipeline_run_id,
                    owner_user_id,
                )
            if self._run_repo and owner_user_id:
                try:
                    self._run_repo.save_pipeline_run(
                        PipelineRun(
                            id=pipeline_run_id,
                            stage_run_id=stage_run_id,
                            pipeline_id=pipeline_id,
                            status="succeeded",
                            owner_user_id=owner_user_id,
                            job_run_id=job_run_id,
                            started_at=datetime.now(timezone.utc),
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                except Exception as e:
                    logger.exception(
                        "job_execution_save_pipeline_run_failed | pipeline_run_id={} error={}",
                        pipeline_run_id,
                        e,
                    )
        except Exception as e:
            if self._run_repo and owner_user_id:
                try:
                    self._run_repo.save_pipeline_run(
                        PipelineRun(
                            id=pipeline_run_id,
                            stage_run_id=stage_run_id,
                            pipeline_id=pipeline_id,
                            status="failed",
                            owner_user_id=owner_user_id,
                            job_run_id=job_run_id,
                            started_at=datetime.now(timezone.utc),
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                except Exception as save_err:
                    logger.exception(
                        "job_execution_save_pipeline_run_failed | pipeline_run_id={} error={}",
                        pipeline_run_id,
                        save_err,
                    )
            raise

    def _run_parallel_pipelines(
        self,
        pipelines_data: list[dict[str, Any]],
        ctx: ExecutionContext,
        snapshot: dict[str, Any],
        stage_id: str,
        job_run_id: str,
        stage_run_id: str,
        owner_user_id: str | None,
    ) -> None:
        """
        Run pipelines in parallel via ThreadPoolExecutor.
        NOTE: Under shared Supabase client, parallel execution can trigger Errno 11
        (connection contention). Bootstrap job uses sequential mode as temporary
        mitigation. See td-2026-03-15-resource-constraints-db-connections-threads.
        """
        errors: list[tuple[str, Exception]] = []
        with ThreadPoolExecutor(max_workers=len(pipelines_data)) as executor:
            futures = {
                executor.submit(
                    self._run_pipeline,
                    p,
                    ctx,
                    snapshot,
                    stage_id,
                    job_run_id,
                    stage_run_id,
                    owner_user_id,
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
        job_run_id: str,
        stage_run_id: str,
        pipeline_run_id: str,
        owner_user_id: str | None,
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

        step_run_id = f"{pipeline_run_id}_step_{step_id}"
        if self._run_repo and owner_user_id:
            try:
                self._run_repo.save_step_run(
                    StepRun(
                        id=step_run_id,
                        pipeline_run_id=pipeline_run_id,
                        step_id=step_id,
                        step_template_id=step_template_id,
                        status="running",
                        owner_user_id=owner_user_id,
                        job_run_id=job_run_id,
                        stage_run_id=stage_run_id,
                        started_at=datetime.now(timezone.utc),
                    )
                )
            except Exception as e:
                logger.exception(
                    "job_execution_save_step_run_failed | step_run_id={} error={}",
                    step_run_id,
                    e,
                )

        ctx.step_run_id = step_run_id

        logger.debug(
            "job_execution_step_start | run_id={} stage_id={} pipeline_id={} step_id={} template={}",
            ctx.run_id,
            stage_id,
            pipeline_id,
            step_id,
            step_template_id,
        )

        try:
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

            if self._run_repo and owner_user_id:
                try:
                    self._run_repo.save_step_run(
                        StepRun(
                            id=step_run_id,
                            pipeline_run_id=pipeline_run_id,
                            step_id=step_id,
                            step_template_id=step_template_id,
                            status="succeeded",
                            owner_user_id=owner_user_id,
                            job_run_id=job_run_id,
                            stage_run_id=stage_run_id,
                            started_at=datetime.now(timezone.utc),
                            completed_at=datetime.now(timezone.utc),
                        )
                    )
                except Exception as e:
                    logger.exception(
                        "job_execution_save_step_run_failed | step_run_id={} error={}",
                        step_run_id,
                        e,
                    )
        except Exception as e:
            if self._run_repo and owner_user_id:
                try:
                    self._run_repo.save_step_run(
                        StepRun(
                            id=step_run_id,
                            pipeline_run_id=pipeline_run_id,
                            step_id=step_id,
                            step_template_id=step_template_id,
                            status="failed",
                            owner_user_id=owner_user_id,
                            job_run_id=job_run_id,
                            stage_run_id=stage_run_id,
                            started_at=datetime.now(timezone.utc),
                            completed_at=datetime.now(timezone.utc),
                            error_summary=str(e)[:500],
                        )
                    )
                except Exception as save_err:
                    logger.exception(
                        "job_execution_save_step_run_failed | step_run_id={} error={}",
                        step_run_id,
                        save_err,
                    )
            raise
