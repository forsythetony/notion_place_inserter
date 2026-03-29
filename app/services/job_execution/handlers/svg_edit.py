"""SVG Edit: fetch SVG URL, tint, upload to R2 icons/beta."""

from __future__ import annotations

import json
from typing import Any

from app.services.job_execution.runtime_types import (
    ExecutionContext,
    StepExecutionHandle,
    StepExecutionResult,
)
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.svg_edit_service import SvgEditService

_CONFIG_PREVIEW_MAX = 800


def _preview(s: str, *, max_len: int = _CONFIG_PREVIEW_MAX) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _config_summary_for_log(config: dict[str, Any], *, source_url: str) -> str:
    tint = config.get("tint_color", "")
    timeout_ms = config.get("timeout_ms")
    return (
        f"tint_color={tint!r}, timeout_ms={timeout_ms!r}, "
        f"source_url_preview={_preview(str(source_url))!r}"
    )


class SvgEditHandler(StepRuntime):
    """Fetch SVG from bound URL, apply tint from config, upload to R2, output image_url."""

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
        raw_url = resolved_inputs.get("image_url")
        if raw_url is None:
            raw_url = resolved_inputs.get("value")

        if isinstance(raw_url, dict):
            ext = raw_url.get("external") or {}
            if isinstance(ext, dict) and ext.get("url"):
                raw_url = ext["url"]
            else:
                raw_url = None

        url = str(raw_url).strip() if raw_url is not None else ""
        if not url:
            step_handle.log_processing("SVG Edit: empty image_url; skipping.")
            return StepExecutionResult(
                outputs={"image_url": ""},
                outcome="degraded",
                error_message="Missing image_url input",
                error_detail={"reason": "missing_image_url"},
            )

        tint = config.get("tint_color", "#000000")
        if isinstance(tint, str):
            tint = tint.strip()
        else:
            tint = str(tint) if tint is not None else ""

        if not tint:
            step_handle.log_processing("SVG Edit: empty tint_color.")
            return StepExecutionResult(
                outputs={"image_url": ""},
                outcome="degraded",
                error_message="Missing tint_color",
                error_detail={"reason": "missing_tint_color"},
            )

        svc = ctx.get_service("svg_edit")
        if not isinstance(svc, SvgEditService):
            step_handle.log_processing("SVG Edit: svg_edit service unavailable.")
            return StepExecutionResult(
                outputs={"image_url": ""},
                outcome="degraded",
                error_message="SvgEditService not configured",
                error_detail={"reason": "svg_edit_unavailable"},
            )

        step_handle.log_step_runtime_calling_service(
            service_label="svg_edit",
            operation="fetch_tint_upload",
            config_summary=_config_summary_for_log(config, source_url=url),
        )

        dry_run = bool(getattr(ctx, "dry_run", False))
        allow_writes = bool(getattr(ctx, "allow_destination_writes", True))

        result = await svc.fetch_tint_upload(
            source_url=url,
            tint_hex=tint,
            step_handle=step_handle,
            dry_run=dry_run,
            allow_destination_writes=allow_writes,
        )

        if result.get("ok"):
            out_url = str(result.get("image_url") or "")
            step_handle.log_step_runtime_received_success()
            if result.get("passthrough"):
                step_handle.log_processing(
                    "[StepRuntime] Passthrough URL (no R2 upload); output image_url set."
                )
            return StepExecutionResult(outputs={"image_url": out_url})

        err = result.get("error_detail") or {}
        reason = err.get("reason", "unknown")
        step_handle.log_processing(
            f"[StepRuntime] SvgEditService did not complete ok: {json.dumps(err, default=str)}"
        )
        return StepExecutionResult(
            outputs={"image_url": ""},
            outcome="degraded",
            error_message=f"SVG edit failed: {reason}",
            error_detail=err if isinstance(err, dict) else {"reason": str(err)},
        )
