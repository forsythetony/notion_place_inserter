"""Search first-party icon library (Postgres + R2)."""

from __future__ import annotations

from typing import Any

from app.services.icon_catalog_service import normalize_icon_query
from app.services.job_execution.runtime_types import (
    ExecutionContext,
    StepExecutionHandle,
    StepExecutionResult,
)
from app.services.job_execution.step_runtime_base import StepRuntime

_EMPTY_ICON_OUTPUTS: dict[str, Any] = {
    "image_url": "",
    "icon_asset_id": None,
    "match_score": None,
    "matched_tags": [],
}


class SearchIconLibraryHandler(StepRuntime):
    """Search internal SVG icon catalog by tag relevance; log misses below threshold."""

    async def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        input_bindings: dict[str, Any],
        resolved_inputs: dict[str, Any],
        ctx: ExecutionContext,
        step_handle: StepExecutionHandle,
        snapshot: dict[str, Any],
    ) -> StepExecutionResult:
        query = resolved_inputs.get("query") or ""
        if not isinstance(query, str):
            query = str(query).strip() if query else ""
        query_stripped = query.strip()
        if not query_stripped:
            step_handle.log_processing("Empty query; skipping icon library search.")
            return StepExecutionResult(outputs=dict(_EMPTY_ICON_OUTPUTS))

        svc = ctx.get_service("icon_catalog")
        if not svc:
            step_handle.log_processing("Icon catalog service unavailable; no icon URL.")
            return StepExecutionResult(
                outputs=dict(_EMPTY_ICON_OUTPUTS),
                outcome="degraded",
                error_message="Icon catalog service unavailable",
                error_detail={"reason": "icon_catalog_unavailable"},
                warnings=["icon_catalog service not configured on execution context"],
            )

        min_score = float(config.get("minimum_match_score", 0.8))
        color_pref = config.get("color_style_preference")
        if isinstance(color_pref, str) and color_pref.strip():
            color_style: str | None = color_pref.strip()
        else:
            color_style = None
        record_miss = config.get("record_miss", True)
        if isinstance(record_miss, str):
            record_miss = record_miss.lower() in ("1", "true", "yes")

        step_handle.log_processing(
            f"Icon library search (normalized={normalize_icon_query(query_stripped)!r}, "
            f"color_style={color_style!r}, min_score={min_score})"
        )

        try:
            matches = await svc.search_icons(
                query_stripped, color_style=color_style, limit=5
            )
        except Exception as exc:
            step_handle.log_processing(f"Icon library search failed: {exc!r}")
            return StepExecutionResult(
                outputs=dict(_EMPTY_ICON_OUTPUTS),
                outcome="degraded",
                error_message=f"Icon library search failed: {exc}",
                error_detail={
                    "reason": "search_icons_error",
                    "exception_type": type(exc).__name__,
                },
                warnings=[str(exc)[:500]],
            )

        if not matches:
            if record_miss:
                try:
                    await svc.record_miss(
                        raw_query=query_stripped,
                        requested_color_style=color_style,
                        source="runtime_step",
                        job_id=ctx.job_id,
                        job_run_id=ctx.run_id,
                        step_id=step_id,
                        example_context={"template": "step_template_search_icon_library"},
                    )
                except Exception as exc:
                    step_handle.log_processing(f"record_miss failed: {exc!r}")
                    return StepExecutionResult(
                        outputs=dict(_EMPTY_ICON_OUTPUTS),
                        outcome="degraded",
                        error_message=f"record_miss failed: {exc}",
                        error_detail={
                            "reason": "record_miss_error",
                            "exception_type": type(exc).__name__,
                        },
                        warnings=[str(exc)[:500]],
                    )
            step_handle.log_processing("No tag matches for icon library search.")
            return StepExecutionResult(outputs=dict(_EMPTY_ICON_OUTPUTS))

        top = matches[0]
        score = float(top.get("score") or 0.0)
        if score < min_score:
            if record_miss:
                try:
                    await svc.record_miss(
                        raw_query=query_stripped,
                        requested_color_style=color_style,
                        source="runtime_step",
                        job_id=ctx.job_id,
                        job_run_id=ctx.run_id,
                        step_id=step_id,
                        example_context={
                            "top_score": score,
                            "minimum_match_score": min_score,
                        },
                    )
                except Exception as exc:
                    step_handle.log_processing(f"record_miss failed: {exc!r}")
                    return StepExecutionResult(
                        outputs={
                            "image_url": "",
                            "icon_asset_id": top.get("icon_asset_id"),
                            "match_score": score,
                            "matched_tags": top.get("matched_tags") or [],
                        },
                        outcome="degraded",
                        error_message=f"record_miss failed: {exc}",
                        error_detail={
                            "reason": "record_miss_error",
                            "exception_type": type(exc).__name__,
                        },
                        warnings=[str(exc)[:500]],
                    )
            step_handle.log_processing(
                f"Best match score {score:.4f} below threshold {min_score:.4f}; miss recorded."
            )
            return StepExecutionResult(
                outputs={
                    "image_url": "",
                    "icon_asset_id": top.get("icon_asset_id"),
                    "match_score": score,
                    "matched_tags": top.get("matched_tags") or [],
                }
            )

        step_handle.log_processing(
            f"Icon library hit: asset={top.get('icon_asset_id')} score={score:.4f}"
        )
        return StepExecutionResult(
            outputs={
                "image_url": top.get("public_url") or "",
                "icon_asset_id": top.get("icon_asset_id"),
                "match_score": score,
                "matched_tags": top.get("matched_tags") or [],
            }
        )
