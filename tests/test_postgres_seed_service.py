"""Unit tests for PostgresBootstrapProvisioningService (ensure_owner_starter_definitions)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.postgres_seed_service import (
    AUTO_SEEDED_DISPLAY_SUFFIX,
    PostgresBootstrapProvisioningService,
    _append_auto_seeded_label,
    _apply_auto_seeded_labels,
)
from app.domain.jobs import JobDefinition, PipelineDefinition, StageDefinition
from app.domain.triggers import TriggerDefinition
from app.services.validation_service import JobGraph


def test_append_auto_seeded_label_idempotent():
    assert _append_auto_seeded_label("Foo") == f"Foo{AUTO_SEEDED_DISPLAY_SUFFIX}"
    doubled = _append_auto_seeded_label("Foo")
    assert _append_auto_seeded_label(doubled) == doubled


def test_apply_auto_seeded_labels_job_and_pipelines():
    tr = TriggerDefinition(
        id="t1",
        owner_user_id="u",
        trigger_type="http",
        display_name="HTTP Trigger",
        path="/p",
        method="POST",
        request_body_schema={"type": "object"},
        status="active",
        auth_mode="bearer",
        secret_value="x",
    )
    job = JobDefinition(
        id="j1",
        owner_user_id="u",
        display_name="My Job",
        target_id="d1",
        status="active",
        stage_ids=["s1"],
    )
    st = StageDefinition(
        id="s1",
        job_id="j1",
        display_name="Stage",
        sequence=1,
        pipeline_ids=["p1"],
    )
    pl = PipelineDefinition(
        id="p1",
        stage_id="s1",
        display_name="Pipeline One",
        sequence=1,
        step_ids=[],
    )
    graph = JobGraph(job=job, stages=[st], pipelines=[pl], steps=[])
    _apply_auto_seeded_labels(tr, graph)
    assert tr.display_name.endswith(AUTO_SEEDED_DISPLAY_SUFFIX)
    assert job.display_name.endswith(AUTO_SEEDED_DISPLAY_SUFFIX)
    assert pl.display_name.endswith(AUTO_SEEDED_DISPLAY_SUFFIX)
    assert st.display_name == "Stage"


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_link_repo():
    link_repo = MagicMock()
    link_repo.attach = AsyncMock()
    return link_repo


@pytest.fixture
def service(mock_client, mock_link_repo):
    svc = PostgresBootstrapProvisioningService(mock_client, link_repo=mock_link_repo)
    svc._app_config.seed_user_limits_from_defaults_if_missing = AsyncMock()
    return svc


async def test_ensure_owner_starter_definitions_saves_job_before_trigger(service):
    """Job graph must be saved before trigger to satisfy trigger_definitions.fk_job."""
    mock_connector = MagicMock()
    mock_connector.get_by_id = AsyncMock(return_value=None)
    mock_connector.save = AsyncMock()
    mock_target = MagicMock()
    mock_target.get_by_id = AsyncMock(return_value=None)
    mock_target.save = AsyncMock()
    mock_trigger = MagicMock()
    mock_trigger.get_by_path = AsyncMock(return_value=None)
    mock_trigger.save = AsyncMock()
    mock_job = MagicMock()
    mock_step_templates = MagicMock()
    mock_step_templates.get_by_id = AsyncMock(return_value=object())

    call_order = []

    async def record_job_save(*args, **kwargs):
        call_order.append("job")

    async def record_trigger_save(*args, **kwargs):
        call_order.append("trigger")

    mock_job.save_job_graph = AsyncMock(side_effect=record_job_save)
    mock_trigger.save = AsyncMock(side_effect=record_trigger_save)

    with (
        patch.object(service, "_connector_instances", mock_connector),
        patch.object(service, "_targets", mock_target),
        patch.object(service, "_triggers", mock_trigger),
        patch.object(service, "_jobs", mock_job),
        patch.object(service, "_step_templates", mock_step_templates),
    ):
        await service.ensure_owner_starter_definitions("871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")

    assert call_order == ["job", "trigger"], "Job must be saved before trigger (fk_job constraint)"


async def test_ensure_owner_starter_definitions_idempotent_when_trigger_exists(service):
    """When trigger already exists, no save calls occur."""
    mock_trigger = MagicMock()
    mock_trigger.get_by_path = AsyncMock(return_value=MagicMock())
    mock_trigger.save = AsyncMock()
    mock_job = MagicMock()
    mock_job.save_job_graph = AsyncMock()

    with (
        patch.object(service, "_connector_instances", MagicMock()),
        patch.object(service, "_targets", MagicMock()),
        patch.object(service, "_triggers", mock_trigger),
        patch.object(service, "_jobs", mock_job),
    ):
        await service.ensure_owner_starter_definitions("871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")

    mock_trigger.save.assert_not_awaited()
    mock_job.save_job_graph.assert_not_awaited()


async def test_ensure_owner_starter_definitions_invalid_owner_exits_without_save(service):
    """Non-UUID owner exits early without any save calls."""
    mock_trigger = MagicMock()
    mock_trigger.save = AsyncMock()
    mock_job = MagicMock()
    mock_job.save_job_graph = AsyncMock()

    with (
        patch.object(service, "_connector_instances", MagicMock()),
        patch.object(service, "_targets", MagicMock()),
        patch.object(service, "_triggers", mock_trigger),
        patch.object(service, "_jobs", mock_job),
    ):
        await service.ensure_owner_starter_definitions("not-a-valid-uuid")

    mock_trigger.save.assert_not_awaited()
    mock_job.save_job_graph.assert_not_awaited()


async def test_ensure_owner_starter_definitions_backfills_missing_step_template(service):
    """Missing catalog step template is provisioned before job graph save."""
    mock_connector = MagicMock()
    mock_connector.get_by_id = AsyncMock(return_value=None)
    mock_connector.save = AsyncMock()
    mock_target = MagicMock()
    mock_target.get_by_id = AsyncMock(return_value=None)
    mock_target.save = AsyncMock()
    mock_trigger = MagicMock()
    mock_trigger.get_by_path = AsyncMock(return_value=None)
    mock_trigger.save = AsyncMock()
    mock_job = MagicMock()
    mock_job.save_job_graph = AsyncMock()
    mock_step_templates = MagicMock()
    mock_step_templates.save = AsyncMock()

    async def _template_exists(template_id: str):
        return None if template_id == "step_template_templater" else object()

    mock_step_templates.get_by_id = AsyncMock(side_effect=_template_exists)

    with (
        patch.object(service, "_connector_instances", mock_connector),
        patch.object(service, "_targets", mock_target),
        patch.object(service, "_triggers", mock_trigger),
        patch.object(service, "_jobs", mock_job),
        patch.object(service, "_step_templates", mock_step_templates),
    ):
        await service.ensure_owner_starter_definitions("871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")

    mock_step_templates.save.assert_awaited_once()
    saved_template = mock_step_templates.save.call_args.args[0]
    assert saved_template.id == "step_template_templater"
    mock_job.save_job_graph.assert_awaited_once()


async def test_reprovision_owner_starter_definitions_deletes_trigger_and_job_then_provisions(service):
    """Reprovision removes /locations trigger and starter job, then saves graph + trigger + link."""
    uid = "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde"
    mock_connector = MagicMock()
    mock_connector.get_by_id = AsyncMock(return_value=object())
    mock_target = MagicMock()
    mock_target.get_by_id = AsyncMock(return_value=object())
    mock_trigger = MagicMock()
    existing = MagicMock()
    existing.id = "trigger_http_locations"
    mock_trigger.get_by_path = AsyncMock(return_value=existing)
    mock_job = MagicMock()
    mock_job.get_graph_by_id = AsyncMock(return_value=object())  # starter job exists
    mock_step_templates = MagicMock()
    mock_step_templates.get_by_id = AsyncMock(return_value=object())

    call_order: list[str] = []

    async def record_delete_trigger(*_a, **_k):
        call_order.append("delete_trigger")

    async def record_delete_job(*_a, **_k):
        call_order.append("delete_job")

    async def record_job_save(*_a, **_k):
        call_order.append("job")

    async def record_trigger_save(*_a, **_k):
        call_order.append("trigger")

    mock_trigger.delete = AsyncMock(side_effect=record_delete_trigger)
    mock_job.delete = AsyncMock(side_effect=record_delete_job)
    mock_job.save_job_graph = AsyncMock(side_effect=record_job_save)
    mock_trigger.save = AsyncMock(side_effect=record_trigger_save)

    with (
        patch.object(service, "_connector_instances", mock_connector),
        patch.object(service, "_targets", mock_target),
        patch.object(service, "_triggers", mock_trigger),
        patch.object(service, "_jobs", mock_job),
        patch.object(service, "_step_templates", mock_step_templates),
    ):
        await service.reprovision_owner_starter_definitions(uid)

    mock_trigger.get_by_path.assert_awaited_once_with("/locations", uid)
    mock_trigger.delete.assert_awaited_once_with("trigger_http_locations", uid)
    mock_job.get_graph_by_id.assert_awaited_once_with("job_notion_place_inserter", uid)
    mock_job.delete.assert_awaited_once_with("job_notion_place_inserter", uid)
    assert call_order[:2] == ["delete_trigger", "delete_job"]
    assert "job" in call_order and "trigger" in call_order
    mock_job.save_job_graph.assert_awaited_once()
    service._link_repo.attach.assert_awaited_once()
