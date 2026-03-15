"""Unit tests for PostgresBootstrapProvisioningService (ensure_owner_starter_definitions)."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.postgres_seed_service import PostgresBootstrapProvisioningService


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def service(mock_client):
    return PostgresBootstrapProvisioningService(mock_client)


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
