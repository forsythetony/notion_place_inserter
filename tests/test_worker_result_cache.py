"""Tests for worker result payload cache (CACHE_RESULTS fast path)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.job_execution.job_execution_service import JobExecutionService
from app.services.worker_result_cache import (
    CachedNotionWritePayload,
    WorkerResultPayloadCache,
    build_worker_result_cache_key,
    parse_cache_results_enabled,
    parse_cache_results_ttl_seconds,
)


def test_parse_cache_results_enabled():
    assert parse_cache_results_enabled("1") is True
    assert parse_cache_results_enabled("true") is True
    assert parse_cache_results_enabled("") is False
    assert parse_cache_results_enabled(None) is False


def test_parse_cache_results_ttl_seconds():
    assert parse_cache_results_ttl_seconds(None) == 300.0
    assert parse_cache_results_ttl_seconds("600") == 600.0
    assert parse_cache_results_ttl_seconds("bad", default=300.0) == 300.0


def test_build_worker_result_cache_key_stable_order():
    k1 = build_worker_result_cache_key(
        owner_user_id="u1",
        definition_snapshot_ref="snap:a",
        data_source_id="ds-1",
        trigger_payload={"keywords": "a", "raw_input": "a"},
        dry_run=False,
        invocation_source=None,
    )
    k2 = build_worker_result_cache_key(
        owner_user_id="u1",
        definition_snapshot_ref="snap:a",
        data_source_id="ds-1",
        trigger_payload={"raw_input": "a", "keywords": "a"},
        dry_run=False,
        invocation_source=None,
    )
    assert k1 == k2


def test_build_worker_result_cache_key_differs_by_payload():
    k1 = build_worker_result_cache_key(
        owner_user_id="u1",
        definition_snapshot_ref="snap:a",
        data_source_id="ds-1",
        trigger_payload={"keywords": "foo"},
        dry_run=False,
        invocation_source=None,
    )
    k2 = build_worker_result_cache_key(
        owner_user_id="u1",
        definition_snapshot_ref="snap:a",
        data_source_id="ds-1",
        trigger_payload={"keywords": "bar"},
        dry_run=False,
        invocation_source=None,
    )
    assert k1 != k2


def test_worker_result_payload_cache_ttl_expiry():
    cache = WorkerResultPayloadCache(ttl_seconds=300.0)
    payload = CachedNotionWritePayload(
        notion_properties={"x": "y"},
        icon=None,
        cover=None,
    )
    with patch(
        "app.services.worker_result_cache.time.monotonic",
        side_effect=[0.0, 0.0, 500.0],
    ):
        cache.set("k", payload)
        assert cache.get("k") is not None
        assert cache.get("k") is None


@pytest.mark.asyncio
async def test_execute_snapshot_run_cache_hit_skips_stages():
    """Second identical logical request skips pipeline stages but still creates a Notion page."""
    notion = MagicMock()
    notion.create_page.return_value = {"id": "page-1", "object": "page"}
    cache = WorkerResultPayloadCache(ttl_seconds=300.0)
    svc = JobExecutionService(
        notion_service=notion,
        dry_run=False,
        result_cache=cache,
    )

    snapshot = {
        "job": {
            "stages": [
                {
                    "id": "stage_property_setting",
                    "sequence": 1,
                    "pipeline_run_mode": "parallel",
                    "pipelines": [
                        {
                            "id": "pipeline_tags",
                            "sequence": 1,
                            "steps": [
                                {
                                    "id": "step_tags",
                                    "step_template_id": "step_template_property_set",
                                    "sequence": 1,
                                    "input_bindings": {"value": {"static_value": ["History"]}},
                                    "config": {"schema_property_id": "prop_tags"},
                                },
                            ],
                        },
                    ],
                },
            ]
        },
        "target": {"display_name": "Places", "external_target_id": "ds-cache-1"},
        "active_schema": {
            "properties": [
                {
                    "id": "prop_tags",
                    "external_property_id": "tags",
                    "property_type": "multi_select",
                    "options": [{"id": "o1", "name": "History"}],
                },
            ],
        },
    }

    trigger = {"keywords": "terminal bar in minneapolis", "raw_input": "terminal bar in minneapolis"}

    with (
        patch.object(
            JobExecutionService,
            "_run_parallel_pipelines",
            new_callable=AsyncMock,
        ) as mock_rp,
        patch(
            "app.services.job_execution.job_execution_service.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        await svc.execute_snapshot_run(
            snapshot=snapshot,
            run_id="run-1",
            job_id="job-1",
            trigger_payload=trigger,
            owner_user_id="user-cache-1",
            definition_snapshot_ref="job_snapshot:user-cache-1:job1:abc123",
        )
        await svc.execute_snapshot_run(
            snapshot=snapshot,
            run_id="run-2",
            job_id="job-2",
            trigger_payload=trigger,
            owner_user_id="user-cache-1",
            definition_snapshot_ref="job_snapshot:user-cache-1:job1:abc123",
        )

    assert mock_rp.call_count == 1
    assert notion.create_page.call_count == 2


@pytest.mark.asyncio
async def test_execute_snapshot_run_scope_boundary_bypasses_cache():
    """Live-test scope should not read or write worker result cache."""
    notion = MagicMock()
    notion.create_page.return_value = {"id": "page-1", "object": "page"}
    cache = WorkerResultPayloadCache(ttl_seconds=300.0)
    svc = JobExecutionService(
        notion_service=notion,
        dry_run=False,
        result_cache=cache,
    )

    snapshot = {
        "job": {
            "stages": [
                {
                    "id": "stage_property_setting",
                    "sequence": 1,
                    "pipeline_run_mode": "parallel",
                    "pipelines": [
                        {
                            "id": "pipeline_tags",
                            "sequence": 1,
                            "steps": [
                                {
                                    "id": "step_tags",
                                    "step_template_id": "step_template_property_set",
                                    "sequence": 1,
                                    "input_bindings": {"value": {"static_value": ["History"]}},
                                    "config": {"schema_property_id": "prop_tags"},
                                },
                            ],
                        },
                    ],
                },
            ]
        },
        "target": {"display_name": "Places", "external_target_id": "ds-scope"},
        "active_schema": {
            "properties": [
                {
                    "id": "prop_tags",
                    "external_property_id": "tags",
                    "property_type": "multi_select",
                    "options": [{"id": "o1", "name": "History"}],
                },
            ],
        },
    }

    trigger = {"keywords": "x"}

    with patch.object(
        JobExecutionService,
        "_run_parallel_pipelines",
        new_callable=AsyncMock,
    ) as mock_rp:
        await svc.execute_snapshot_run(
            snapshot=snapshot,
            run_id="run-1",
            job_id="job-1",
            trigger_payload=trigger,
            owner_user_id="user-scope",
            definition_snapshot_ref="snap-scope",
            scope_boundary={"stage_ids": ["stage_property_setting"]},
        )
        await svc.execute_snapshot_run(
            snapshot=snapshot,
            run_id="run-2",
            job_id="job-2",
            trigger_payload=trigger,
            owner_user_id="user-scope",
            definition_snapshot_ref="snap-scope",
            scope_boundary={"stage_ids": ["stage_property_setting"]},
        )

    assert mock_rp.call_count == 2


@pytest.mark.asyncio
async def test_execute_snapshot_run_without_result_cache_runs_stages_each_time():
    notion = MagicMock()
    notion.create_page.return_value = {"id": "page-1", "object": "page"}
    svc = JobExecutionService(notion_service=notion, dry_run=False, result_cache=None)

    snapshot = {
        "job": {
            "stages": [
                {
                    "id": "stage_property_setting",
                    "sequence": 1,
                    "pipeline_run_mode": "parallel",
                    "pipelines": [
                        {
                            "id": "pipeline_tags",
                            "sequence": 1,
                            "steps": [
                                {
                                    "id": "step_tags",
                                    "step_template_id": "step_template_property_set",
                                    "sequence": 1,
                                    "input_bindings": {"value": {"static_value": ["History"]}},
                                    "config": {"schema_property_id": "prop_tags"},
                                },
                            ],
                        },
                    ],
                },
            ]
        },
        "target": {"display_name": "Places", "external_target_id": "ds-nocache"},
        "active_schema": {
            "properties": [
                {
                    "id": "prop_tags",
                    "external_property_id": "tags",
                    "property_type": "multi_select",
                    "options": [{"id": "o1", "name": "History"}],
                },
            ],
        },
    }

    with patch.object(
        JobExecutionService,
        "_run_parallel_pipelines",
        new_callable=AsyncMock,
    ) as mock_rp:
        await svc.execute_snapshot_run(
            snapshot=snapshot,
            run_id="run-1",
            job_id="job-1",
            trigger_payload={"keywords": "a"},
            owner_user_id="u1",
            definition_snapshot_ref="snap-1",
        )
        await svc.execute_snapshot_run(
            snapshot=snapshot,
            run_id="run-2",
            job_id="job-2",
            trigger_payload={"keywords": "a"},
            owner_user_id="u1",
            definition_snapshot_ref="snap-1",
        )

    assert mock_rp.call_count == 2
