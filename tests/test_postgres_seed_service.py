"""Unit tests for PostgresBootstrapProvisioningService (ensure_owner_starter_definitions)."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.postgres_seed_service import PostgresBootstrapProvisioningService


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_link_repo():
    link_repo = MagicMock()
    link_repo.attach = MagicMock()
    return link_repo


@pytest.fixture
def service(mock_client, mock_link_repo):
    return PostgresBootstrapProvisioningService(mock_client, link_repo=mock_link_repo)


def test_ensure_owner_starter_definitions_saves_job_before_trigger(service):
    """Job graph must be saved before trigger to satisfy trigger_definitions.fk_job."""
    mock_connector = MagicMock()
    mock_connector.get_by_id.return_value = None
    mock_target = MagicMock()
    mock_target.get_by_id.return_value = None
    mock_trigger = MagicMock()
    mock_trigger.get_by_path.return_value = None
    mock_job = MagicMock()
    mock_step_templates = MagicMock()
    mock_step_templates.get_by_id.return_value = object()

    call_order = []

    def record_job_save(*args, **kwargs):
        call_order.append("job")

    def record_trigger_save(*args, **kwargs):
        call_order.append("trigger")

    mock_job.save_job_graph.side_effect = record_job_save
    mock_trigger.save.side_effect = record_trigger_save

    with (
        patch.object(service, "_connector_instances", mock_connector),
        patch.object(service, "_targets", mock_target),
        patch.object(service, "_triggers", mock_trigger),
        patch.object(service, "_jobs", mock_job),
        patch.object(service, "_step_templates", mock_step_templates),
    ):
        service.ensure_owner_starter_definitions("871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")

    assert call_order == ["job", "trigger"], "Job must be saved before trigger (fk_job constraint)"


def test_ensure_owner_starter_definitions_idempotent_when_trigger_exists(service):
    """When trigger already exists, no save calls occur."""
    mock_trigger = MagicMock()
    mock_trigger.get_by_path.return_value = MagicMock()
    mock_job = MagicMock()

    with (
        patch.object(service, "_connector_instances", MagicMock()),
        patch.object(service, "_targets", MagicMock()),
        patch.object(service, "_triggers", mock_trigger),
        patch.object(service, "_jobs", mock_job),
    ):
        service.ensure_owner_starter_definitions("871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")

    mock_trigger.save.assert_not_called()
    mock_job.save_job_graph.assert_not_called()


def test_ensure_owner_starter_definitions_invalid_owner_exits_without_save(service):
    """Non-UUID owner exits early without any save calls."""
    mock_trigger = MagicMock()
    mock_job = MagicMock()

    with (
        patch.object(service, "_connector_instances", MagicMock()),
        patch.object(service, "_targets", MagicMock()),
        patch.object(service, "_triggers", mock_trigger),
        patch.object(service, "_jobs", mock_job),
    ):
        service.ensure_owner_starter_definitions("not-a-valid-uuid")

    mock_trigger.save.assert_not_called()
    mock_job.save_job_graph.assert_not_called()


def test_ensure_owner_starter_definitions_backfills_missing_step_template(service):
    """Missing catalog step template is provisioned before job graph save."""
    mock_connector = MagicMock()
    mock_connector.get_by_id.return_value = None
    mock_target = MagicMock()
    mock_target.get_by_id.return_value = None
    mock_trigger = MagicMock()
    mock_trigger.get_by_path.return_value = None
    mock_job = MagicMock()
    mock_step_templates = MagicMock()

    def _template_exists(template_id: str):
        return None if template_id == "step_template_templater" else object()

    mock_step_templates.get_by_id.side_effect = _template_exists

    with (
        patch.object(service, "_connector_instances", mock_connector),
        patch.object(service, "_targets", mock_target),
        patch.object(service, "_triggers", mock_trigger),
        patch.object(service, "_jobs", mock_job),
        patch.object(service, "_step_templates", mock_step_templates),
    ):
        service.ensure_owner_starter_definitions("871ba2fa-fd5d-4a81-9f0d-0d98b348ccde")

    assert mock_step_templates.save.call_count == 1
    saved_template = mock_step_templates.save.call_args.args[0]
    assert saved_template.id == "step_template_templater"
    mock_job.save_job_graph.assert_called_once()


def test_reprovision_owner_starter_definitions_deletes_trigger_and_job_then_provisions(service):
    """Reprovision removes /locations trigger and starter job, then saves graph + trigger + link."""
    uid = "871ba2fa-fd5d-4a81-9f0d-0d98b348ccde"
    mock_connector = MagicMock()
    mock_connector.get_by_id.return_value = object()
    mock_target = MagicMock()
    mock_target.get_by_id.return_value = object()
    mock_trigger = MagicMock()
    existing = MagicMock()
    existing.id = "trigger_http_locations"
    mock_trigger.get_by_path.return_value = existing
    mock_job = MagicMock()
    mock_job.get_graph_by_id.return_value = object()  # starter job exists
    mock_step_templates = MagicMock()
    mock_step_templates.get_by_id.return_value = object()

    call_order: list[str] = []

    def record_delete_trigger(*_a, **_k):
        call_order.append("delete_trigger")

    def record_delete_job(*_a, **_k):
        call_order.append("delete_job")

    def record_job_save(*_a, **_k):
        call_order.append("job")

    def record_trigger_save(*_a, **_k):
        call_order.append("trigger")

    mock_trigger.delete.side_effect = record_delete_trigger
    mock_job.delete.side_effect = record_delete_job
    mock_job.save_job_graph.side_effect = record_job_save
    mock_trigger.save.side_effect = record_trigger_save

    with (
        patch.object(service, "_connector_instances", mock_connector),
        patch.object(service, "_targets", mock_target),
        patch.object(service, "_triggers", mock_trigger),
        patch.object(service, "_jobs", mock_job),
        patch.object(service, "_step_templates", mock_step_templates),
    ):
        service.reprovision_owner_starter_definitions(uid)

    mock_trigger.get_by_path.assert_called_with("/locations", uid)
    mock_trigger.delete.assert_called_once_with("trigger_http_locations", uid)
    mock_job.get_graph_by_id.assert_called_once_with("job_notion_place_inserter", uid)
    mock_job.delete.assert_called_once_with("job_notion_place_inserter", uid)
    assert call_order[:2] == ["delete_trigger", "delete_job"]
    assert "job" in call_order and "trigger" in call_order
    mock_job.save_job_graph.assert_called_once()
    service._link_repo.attach.assert_called_once()
