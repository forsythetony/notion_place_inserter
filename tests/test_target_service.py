"""Tests for TargetService (p3_pr07)."""

import tempfile
from pathlib import Path

from app.domain import DataTarget, TargetSchemaSnapshot
from app.repositories import YamlTargetRepository, YamlTargetSchemaRepository
from app.services.target_service import TargetService


async def test_target_service_get_with_active_schema_no_schema():
    """TargetService get_with_active_schema returns target without schema when none attached."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        (Path(base) / "tenants" / "u1" / "targets").mkdir(parents=True)
        target_repo = YamlTargetRepository(base=base)
        schema_repo = YamlTargetSchemaRepository(base=base)
        service = TargetService(
            target_repository=target_repo,
            target_schema_repository=schema_repo,
        )

        target = DataTarget(
            id="t1",
            owner_user_id="u1",
            target_template_id="notion_database",
            connector_instance_id="conn_1",
            display_name="Test DB",
            external_target_id="ext_1",
            status="active",
            active_schema_snapshot_id=None,
        )
        await target_repo.save(target)

        result = await service.get_with_active_schema("t1", "u1")
        assert result is not None
        assert result.target.id == "t1"
        assert result.active_schema is None


async def test_target_service_get_with_active_schema_with_snapshot():
    """TargetService get_with_active_schema returns target with schema when attached."""
    from datetime import datetime, timezone

    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        (Path(base) / "tenants" / "u1" / "targets").mkdir(parents=True)
        (Path(base) / "tenants" / "u1" / "target_schema_snapshots").mkdir(parents=True)
        target_repo = YamlTargetRepository(base=base)
        schema_repo = YamlTargetSchemaRepository(base=base)
        service = TargetService(
            target_repository=target_repo,
            target_schema_repository=schema_repo,
        )

        target = DataTarget(
            id="t1",
            owner_user_id="u1",
            target_template_id="notion_database",
            connector_instance_id="conn_1",
            display_name="Test DB",
            external_target_id="ext_1",
            status="active",
            active_schema_snapshot_id="schema_1",
        )
        await target_repo.save(target)

        snapshot = TargetSchemaSnapshot(
            id="schema_1",
            owner_user_id="u1",
            data_target_id="t1",
            version="1",
            fetched_at=datetime.now(timezone.utc),
            is_active=True,
            source_connector_instance_id="conn_1",
            properties=[],
        )
        await schema_repo.save(snapshot)

        result = await service.get_with_active_schema("t1", "u1")
        assert result is not None
        assert result.target.id == "t1"
        assert result.active_schema is not None
        assert result.active_schema.id == "schema_1"


async def test_target_service_get_with_active_schema_missing_target():
    """TargetService get_with_active_schema returns None for unknown target."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        target_repo = YamlTargetRepository(base=base)
        schema_repo = YamlTargetSchemaRepository(base=base)
        service = TargetService(
            target_repository=target_repo,
            target_schema_repository=schema_repo,
        )

        result = await service.get_with_active_schema("nonexistent", "u1")
        assert result is None
