"""SVG edit service and handler tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.job_execution.handlers.svg_edit import SvgEditHandler
from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_error import default_outputs_for_step
from app.services.job_execution.step_pipeline_log import StepPipelineLog
from app.services.r2_media_storage_service import R2MediaStorageService
from app.services.svg_edit_service import (
    SvgEditService,
    normalize_hex_color,
    tint_svg_markup,
)


def test_normalize_hex_color():
    assert normalize_hex_color("#abc") == "#aabbcc"
    assert normalize_hex_color("aabbcc") == "#aabbcc"
    assert normalize_hex_color("#ff00FF") == "#ff00ff"
    assert normalize_hex_color("") is None
    assert normalize_hex_color("not-a-color") is None


def test_tint_svg_markup_current_color_and_hex():
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" stroke="#000000"/></svg>'
    out = tint_svg_markup(svg, "#ff5500")
    assert 'fill="#ff5500"' in out
    assert 'stroke="#ff5500"' in out


def test_tint_svg_markup_skips_none_and_url():
    svg = '<svg><defs><linearGradient id="g"/></defs><path fill="none" stroke="url(#g)"/></svg>'
    out = tint_svg_markup(svg, "#00ff00")
    assert 'fill="none"' in out
    assert 'stroke="url(#g)"' in out


def test_default_outputs_svg_edit():
    assert default_outputs_for_step("step_template_svg_edit", resolved_inputs={}) == {"image_url": ""}


@pytest.mark.asyncio
async def test_svg_edit_handler_success_with_mock_upload():
    pl = StepPipelineLog(
        run_id="r1",
        job_id="j1",
        stage_id="s1",
        pipeline_id="p1",
        step_id="st1",
        step_template_id="step_template_svg_edit",
    )
    handle = StepExecutionHandle(step_run_id="sr1", pipeline_log=pl)
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
        dry_run=False,
        allow_destination_writes=True,
    )

    monkeypatch_storage = MagicMock(spec=R2MediaStorageService)
    monkeypatch_storage.prefixed_object_key = lambda rel: f"oleo/{rel}"
    monkeypatch_storage.public_url_for_key = lambda k: f"https://cdn.example.com/{k}"
    monkeypatch_storage.put_object = MagicMock()

    svc = SvgEditService(monkeypatch_storage)
    ctx._services["svg_edit"] = svc

    svg_bytes = b'<svg xmlns="http://www.w3.org/2000/svg"><path fill="#111111"/></svg>'
    with patch(
        "app.services.svg_edit_service._fetch_svg_bytes",
        new_callable=AsyncMock,
        return_value=svg_bytes,
    ):
        h = SvgEditHandler()
        result = await h.execute(
            "st1",
            {"tint_color": "#ff0000"},
            {},
            {"image_url": "https://example.com/icon.svg"},
            ctx,
            handle,
            {},
        )

    assert result.outcome == "success"
    assert result.outputs["image_url"].startswith("https://cdn.example.com/")
    assert "oleo/icons/beta/" in result.outputs["image_url"] or "icons/beta/" in result.outputs["image_url"]
    monkeypatch_storage.put_object.assert_called_once()
    call_kw = monkeypatch_storage.put_object.call_args.kwargs
    assert call_kw["content_type"] == "image/svg+xml"
    assert b"fill" in call_kw["body"]


@pytest.mark.asyncio
async def test_svg_edit_handler_degraded_invalid_tint():
    pl = StepPipelineLog(
        run_id="r1",
        job_id="j1",
        stage_id="s1",
        pipeline_id="p1",
        step_id="st1",
        step_template_id="step_template_svg_edit",
    )
    handle = StepExecutionHandle(step_run_id="sr1", pipeline_log=pl)
    ctx = ExecutionContext(run_id="r1", job_id="j1", definition_snapshot_ref=None, trigger_payload={})
    ctx._services["svg_edit"] = SvgEditService(None)

    h = SvgEditHandler()
    result = await h.execute(
        "st1",
        {"tint_color": "not-a-color"},
        {},
        {"image_url": "https://example.com/x.svg"},
        ctx,
        handle,
        {},
    )
    assert result.outcome == "degraded"
    assert result.outputs["image_url"] == ""


@pytest.mark.asyncio
async def test_svg_edit_handler_passthrough_dry_run():
    pl = StepPipelineLog(
        run_id="r1",
        job_id="j1",
        stage_id="s1",
        pipeline_id="p1",
        step_id="st1",
        step_template_id="step_template_svg_edit",
    )
    handle = StepExecutionHandle(step_run_id="sr1", pipeline_log=pl)
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
        dry_run=True,
    )
    storage = MagicMock(spec=R2MediaStorageService)
    ctx._services["svg_edit"] = SvgEditService(storage)

    svg_bytes = b'<svg xmlns="http://www.w3.org/2000/svg"><path fill="black"/></svg>'
    with patch(
        "app.services.svg_edit_service._fetch_svg_bytes",
        new_callable=AsyncMock,
        return_value=svg_bytes,
    ):
        h = SvgEditHandler()
        result = await h.execute(
            "st1",
            {"tint_color": "#00ff00"},
            {},
            {"image_url": "https://cdn.io/a.svg"},
            ctx,
            handle,
            {},
        )
    assert result.outcome == "success"
    assert result.outputs["image_url"] == "https://cdn.io/a.svg"
    storage.put_object.assert_not_called()
