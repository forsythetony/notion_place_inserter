"""Tests for SchemaSyncService (p3_pr07)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain import ConnectorInstance, DataTarget
from app.services.schema_sync_service import SchemaSyncService, SchemaSyncServiceError


async def test_schema_sync_service_rejects_plaintext_secrets():
    """SchemaSyncService raises when connector has plaintext secret in config."""
    mock_target_repo = MagicMock()
    mock_schema_repo = MagicMock()
    mock_connector_repo = MagicMock()

    target = DataTarget(
        id="t1",
        owner_user_id="u1",
        target_template_id="notion_database",
        connector_instance_id="conn_1",
        display_name="Places to Visit",
        external_target_id="ext_1",
        status="active",
    )
    connector = ConnectorInstance(
        id="conn_1",
        owner_user_id="u1",
        connector_template_id="notion_oauth",
        display_name="Notion",
        status="active",
        config={"api_key": "sk-xxx"},
        secret_ref=None,
    )

    mock_target_repo.get_by_id = AsyncMock(return_value=target)
    mock_connector_repo.get_by_id = AsyncMock(return_value=connector)

    service = SchemaSyncService(
        target_repository=mock_target_repo,
        target_schema_repository=mock_schema_repo,
        connector_instance_repository=mock_connector_repo,
        notion_service=None,
    )

    with pytest.raises(SchemaSyncServiceError) as exc_info:
        await service.sync_for_target("t1", "u1")
    assert "secret_ref" in str(exc_info.value).lower() or "plaintext" in str(exc_info.value).lower()


async def test_schema_sync_service_rejects_missing_secret_ref():
    """SchemaSyncService raises when connector has no secret_ref."""
    mock_target_repo = MagicMock()
    mock_schema_repo = MagicMock()
    mock_connector_repo = MagicMock()

    target = DataTarget(
        id="t1",
        owner_user_id="u1",
        target_template_id="notion_database",
        connector_instance_id="conn_1",
        display_name="Places to Visit",
        external_target_id="ext_1",
        status="active",
    )
    connector = ConnectorInstance(
        id="conn_1",
        owner_user_id="u1",
        connector_template_id="notion_oauth",
        display_name="Notion",
        status="active",
        config={},
        secret_ref=None,
    )

    mock_target_repo.get_by_id = AsyncMock(return_value=target)
    mock_connector_repo.get_by_id = AsyncMock(return_value=connector)

    service = SchemaSyncService(
        target_repository=mock_target_repo,
        target_schema_repository=mock_schema_repo,
        connector_instance_repository=mock_connector_repo,
        notion_service=None,
    )

    with pytest.raises(SchemaSyncServiceError) as exc_info:
        await service.sync_for_target("t1", "u1")
    assert "secret_ref" in str(exc_info.value).lower()


async def test_schema_sync_service_raises_when_target_not_found():
    """SchemaSyncService raises when target does not exist."""
    mock_target_repo = MagicMock()
    mock_target_repo.get_by_id = AsyncMock(return_value=None)

    service = SchemaSyncService(
        target_repository=mock_target_repo,
        target_schema_repository=MagicMock(),
        connector_instance_repository=MagicMock(),
        notion_service=None,
    )

    with pytest.raises(SchemaSyncServiceError) as exc_info:
        await service.sync_for_target("t1", "u1")
    assert "not found" in str(exc_info.value).lower()


async def test_schema_sync_service_raises_unsupported_target_template():
    """SchemaSyncService raises for unsupported target template."""
    mock_target_repo = MagicMock()
    mock_connector_repo = MagicMock()

    target = DataTarget(
        id="t1",
        owner_user_id="u1",
        target_template_id="unknown_template",
        connector_instance_id="conn_1",
        display_name="Test",
        external_target_id="ext_1",
        status="active",
    )
    connector = ConnectorInstance(
        id="conn_1",
        owner_user_id="u1",
        connector_template_id="x",
        display_name="X",
        status="active",
        config={},
        secret_ref="ENV_NOTION_KEY",
    )

    mock_target_repo.get_by_id = AsyncMock(return_value=target)
    mock_connector_repo.get_by_id = AsyncMock(return_value=connector)

    service = SchemaSyncService(
        target_repository=mock_target_repo,
        target_schema_repository=MagicMock(),
        connector_instance_repository=mock_connector_repo,
        notion_service=None,
    )

    with pytest.raises(SchemaSyncServiceError) as exc_info:
        await service.sync_for_target("t1", "u1")
    assert "not supported" in str(exc_info.value).lower()
