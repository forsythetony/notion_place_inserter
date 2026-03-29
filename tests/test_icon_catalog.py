"""Icon library helpers and runtime step."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.icon_catalog_repository import IconCatalogRepository
from app.services.icon_catalog_service import normalize_icon_query
from app.services.r2_media_storage_service import (
    R2MediaStorageService,
    join_prefixed_object_key,
    normalize_r2_key_prefix,
)
from app.services.job_execution.handlers.search_icon_library import SearchIconLibraryHandler
from app.services.job_execution.runtime_types import (
    ExecutionContext,
    StepExecutionHandle,
    StepExecutionResult,
)
from app.services.job_execution.step_error import default_outputs_for_step
from app.services.job_execution.step_pipeline_log import StepPipelineLog


def test_normalize_icon_query():
    assert normalize_icon_query("  Car-Boat  ") == "car boat"
    assert normalize_icon_query("foo__bar") == "foo bar"


def test_normalize_r2_key_prefix():
    assert normalize_r2_key_prefix("") == ""
    assert normalize_r2_key_prefix(None) == ""
    assert normalize_r2_key_prefix("oleo") == "oleo"
    assert normalize_r2_key_prefix(" /oleo/ ") == "oleo"
    assert normalize_r2_key_prefix("prod/icons") == "prod/icons"


def test_join_prefixed_object_key():
    assert join_prefixed_object_key("", "icons/x/original.svg") == "icons/x/original.svg"
    assert join_prefixed_object_key("oleo", "icons/x/original.svg") == "oleo/icons/x/original.svg"
    assert join_prefixed_object_key("oleo", "/icons/x/original.svg") == "oleo/icons/x/original.svg"


def test_r2_media_storage_prefixed_object_key_and_public_url(monkeypatch):
    monkeypatch.setattr("boto3.client", lambda *a, **k: MagicMock())
    svc = R2MediaStorageService(
        endpoint_url="https://acc.r2.cloudflarestorage.com",
        access_key_id="k",
        secret_access_key="s",
        bucket="b",
        public_base_url="https://cdn.example.com/",
        key_prefix="/oleo/",
    )
    assert svc.key_prefix == "oleo"
    rel = "icons/00000000-0000-0000-0000-000000000001/original.svg"
    full = svc.prefixed_object_key(rel)
    assert full == "oleo/icons/00000000-0000-0000-0000-000000000001/original.svg"
    assert svc.public_url_for_key(full) == (
        "https://cdn.example.com/oleo/icons/00000000-0000-0000-0000-000000000001/original.svg"
    )


def test_default_outputs_search_icon_library():
    out = default_outputs_for_step(
        "step_template_search_icon_library", resolved_inputs={"query": "x"}
    )
    assert out["image_url"] == ""
    assert out["icon_asset_id"] is None
    assert out["match_score"] is None
    assert out["matched_tags"] == []


@pytest.mark.asyncio
async def test_search_icon_library_handler_hit():
    class FakeCatalog:
        async def search_icons(self, query, *, color_style=None, limit=10):
            assert query == "coffee"
            return [
                {
                    "icon_asset_id": "a1",
                    "title": "Cup",
                    "public_url": "https://example.com/x.svg",
                    "color_style": "light",
                    "score": 0.95,
                    "matched_tags": [{"label": "coffee", "normalizedLabel": "coffee", "weight": 1.0}],
                }
            ]

        async def record_miss(self, **kwargs):
            raise AssertionError("should not record miss on hit")

    pl = StepPipelineLog(
        run_id="r1",
        job_id="j1",
        stage_id="s1",
        pipeline_id="p1",
        step_id="st1",
        step_template_id="step_template_search_icon_library",
    )
    handle = StepExecutionHandle(step_run_id="sr1", pipeline_log=pl)
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    ctx._services["icon_catalog"] = FakeCatalog()

    h = SearchIconLibraryHandler()
    out = await h.execute(
        "st1",
        {"minimum_match_score": 0.8},
        {},
        {"query": "coffee"},
        ctx,
        handle,
        {},
    )
    assert isinstance(out, StepExecutionResult)
    assert out.outcome == "success"
    assert out.outputs["image_url"] == "https://example.com/x.svg"
    assert out.outputs["icon_asset_id"] == "a1"
    assert out.outputs["match_score"] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_search_icon_library_handler_miss_below_threshold():
    class FakeCatalog:
        async def search_icons(self, query, *, color_style=None, limit=10):
            return [
                {
                    "icon_asset_id": "a1",
                    "public_url": None,
                    "score": 0.5,
                    "matched_tags": [],
                }
            ]

        async def record_miss(self, **kwargs):
            self.called = True

    fake = FakeCatalog()
    pl = StepPipelineLog(
        run_id="r1",
        job_id="j1",
        stage_id="s1",
        pipeline_id="p1",
        step_id="st1",
        step_template_id="step_template_search_icon_library",
    )
    handle = StepExecutionHandle(step_run_id="sr1", pipeline_log=pl)
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    ctx._services["icon_catalog"] = fake

    h = SearchIconLibraryHandler()
    out = await h.execute(
        "st1",
        {"minimum_match_score": 0.8},
        {},
        {"query": "x"},
        ctx,
        handle,
        {},
    )
    assert isinstance(out, StepExecutionResult)
    assert out.outcome == "success"
    assert out.outputs["image_url"] == ""
    assert getattr(fake, "called", False) is True


@pytest.mark.asyncio
async def test_search_icon_library_handler_miss_no_matches_prefixed_runtime_ids():
    """No tag matches: record_miss receives loc_* job_id and string run_id (DB columns are text)."""

    class FakeCatalog:
        async def search_icons(self, query, *, color_style=None, limit=10):
            assert query == "Nicollet Island Inn"
            return []

        async def record_miss(self, **kwargs):
            self.kwargs = kwargs

    fake = FakeCatalog()
    pl = StepPipelineLog(
        run_id="c3f49e2b-c9b6-432a-8135-3f06f4c36316",
        job_id="loc_3adde6001eeb41ebaebc43eca376de80",
        stage_id="s1",
        pipeline_id="p1",
        step_id="st1",
        step_template_id="step_template_search_icon_library",
    )
    handle = StepExecutionHandle(step_run_id="sr1", pipeline_log=pl)
    ctx = ExecutionContext(
        run_id="c3f49e2b-c9b6-432a-8135-3f06f4c36316",
        job_id="loc_3adde6001eeb41ebaebc43eca376de80",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    ctx._services["icon_catalog"] = fake

    h = SearchIconLibraryHandler()
    out = await h.execute(
        "st1",
        {"minimum_match_score": 0.8},
        {},
        {"query": "Nicollet Island Inn"},
        ctx,
        handle,
        {},
    )
    assert isinstance(out, StepExecutionResult)
    assert out.outcome == "success"
    assert out.outputs["image_url"] == ""
    assert getattr(fake, "kwargs", None) is not None
    assert fake.kwargs["job_id"] == "loc_3adde6001eeb41ebaebc43eca376de80"
    assert fake.kwargs["job_run_id"] == "c3f49e2b-c9b6-432a-8135-3f06f4c36316"
    assert fake.kwargs["raw_query"] == "Nicollet Island Inn"


@pytest.mark.asyncio
async def test_icon_catalog_repository_upsert_search_miss_inserts_prefixed_job_ids():
    """Insert row must carry runtime strings; Postgres uuid columns rejected loc_* before migration."""
    captured: dict = {}

    icon_table = MagicMock()
    select_chain = MagicMock()
    select_chain.select.return_value = select_chain
    select_chain.eq.return_value = select_chain
    select_chain.is_.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.execute = AsyncMock(return_value=MagicMock(data=[]))

    def insert_side_effect(row: dict):
        captured["row"] = row
        ins = MagicMock()
        ins.execute = AsyncMock(return_value=MagicMock(data=[{}]))
        return ins

    icon_table.select = select_chain.select
    icon_table.insert = insert_side_effect

    client = MagicMock()

    def table(name: str):
        assert name == "icon_search_misses"
        return icon_table

    client.table = table

    repo = IconCatalogRepository(client)
    await repo.upsert_search_miss(
        normalized_query="nicollet island inn",
        raw_query="Nicollet Island Inn",
        requested_color_style=None,
        source="runtime_step",
        job_id="loc_3adde6001eeb41ebaebc43eca376de80",
        job_run_id="c3f49e2b-c9b6-432a-8135-3f06f4c36316",
        step_id="st1",
        example_context={"template": "step_template_search_icon_library"},
    )
    assert captured["row"]["job_id"] == "loc_3adde6001eeb41ebaebc43eca376de80"
    assert captured["row"]["job_run_id"] == "c3f49e2b-c9b6-432a-8135-3f06f4c36316"


@pytest.mark.asyncio
async def test_search_icon_library_handler_search_error_degraded():
    class FakeCatalog:
        async def search_icons(self, query, *, color_style=None, limit=10):
            raise RuntimeError("db down")

        async def record_miss(self, **kwargs):
            raise AssertionError("should not record miss")

    pl = StepPipelineLog(
        run_id="r1",
        job_id="j1",
        stage_id="s1",
        pipeline_id="p1",
        step_id="st1",
        step_template_id="step_template_search_icon_library",
    )
    handle = StepExecutionHandle(step_run_id="sr1", pipeline_log=pl)
    ctx = ExecutionContext(
        run_id="r1",
        job_id="j1",
        definition_snapshot_ref=None,
        trigger_payload={},
    )
    ctx._services["icon_catalog"] = FakeCatalog()

    h = SearchIconLibraryHandler()
    out = await h.execute(
        "st1",
        {"minimum_match_score": 0.8},
        {},
        {"query": "coffee"},
        ctx,
        handle,
        {},
    )
    assert isinstance(out, StepExecutionResult)
    assert out.outcome == "degraded"
    assert out.outputs["image_url"] == ""
    assert "db down" in (out.error_message or "")
