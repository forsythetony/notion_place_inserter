"""Tests for JobDefinitionService (p3_pr05)."""

import tempfile
from pathlib import Path

from datetime import datetime, timezone

import pytest

from app.domain import DataTarget, TargetSchemaSnapshot
from app.repositories import (
    YamlJobRepository,
    YamlTargetRepository,
    YamlTargetSchemaRepository,
    YamlTriggerRepository,
)
from app.repositories.yaml_loader import load_yaml_file
from app.services.job_definition_service import (
    JobDefinitionService,
    ResolvedJobSnapshot,
)
from app.services.target_service import TargetService
from app.services.trigger_service import TriggerService


def test_resolved_job_snapshot_is_frozen():
    """ResolvedJobSnapshot is immutable (frozen dataclass)."""
    snap = ResolvedJobSnapshot(
        snapshot_ref="job_snapshot:u1:j1:abc",
        snapshot={"job": {"id": "j1"}},
    )
    with pytest.raises(AttributeError):
        snap.snapshot_ref = "other"
    with pytest.raises(AttributeError):
        snap.snapshot = {}


def test_resolved_job_snapshot_to_dict_returns_copy():
    """to_dict returns defensive copy, not shared reference."""
    inner = {"id": "j1"}
    snap = ResolvedJobSnapshot(
        snapshot_ref="ref",
        snapshot={"job": inner},
    )
    copy = snap.to_dict()
    assert copy["job"]["id"] == "j1"
    copy["job"]["id"] = "modified"
    assert snap.snapshot["job"]["id"] == "j1"


def test_job_definition_service_resolves_bootstrap_job_with_tenant_target():
    """JobDefinitionService resolves complete snapshot when tenant has target."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        (Path(base) / "bootstrap" / "jobs").mkdir(parents=True)
        (Path(base) / "bootstrap" / "triggers").mkdir(parents=True)
        (Path(base) / "tenants" / "user_1" / "targets").mkdir(parents=True)
        (Path(base) / "tenants" / "user_1" / "target_schema_snapshots").mkdir(
            parents=True
        )

        # Copy bootstrap job and trigger
        job_data = load_yaml_file(
            "product_model/bootstrap/jobs/notion_place_inserter.yaml"
        )
        trigger_data = load_yaml_file(
            "product_model/bootstrap/triggers/trigger_http_locations.yaml"
        )
        assert job_data is not None
        assert trigger_data is not None

        from app.repositories.yaml_loader import dump_yaml_file

        dump_yaml_file(
            f"{base}/bootstrap/jobs/notion_place_inserter.yaml",
            job_data,
        )
        dump_yaml_file(
            f"{base}/bootstrap/triggers/trigger_http_locations.yaml",
            trigger_data,
        )

        # Create tenant target target_places_to_visit
        target = DataTarget(
            id="target_places_to_visit",
            owner_user_id="user_1",
            target_template_id="notion_database",
            connector_instance_id="conn_1",
            display_name="Places",
            external_target_id="ext_1",
            status="active",
            active_schema_snapshot_id=None,
        )
        target_repo = YamlTargetRepository(base=base)
        schema_repo = YamlTargetSchemaRepository(base=base)
        target_repo.save(target)

        job_repo = YamlJobRepository(base=base)
        trigger_repo = YamlTriggerRepository(base=base)
        trigger_service = TriggerService(trigger_repository=trigger_repo)
        target_service = TargetService(
            target_repository=target_repo,
            target_schema_repository=schema_repo,
        )
        service = JobDefinitionService(
            job_repository=job_repo,
            trigger_service=trigger_service,
            target_service=target_service,
        )

        snapshot = service.resolve_for_run(
            "job_notion_place_inserter", "user_1", "trigger_http_locations"
        )
        assert snapshot is not None
        assert isinstance(snapshot, ResolvedJobSnapshot)
        assert snapshot.snapshot_ref.startswith("job_snapshot:user_1:job_notion_place_inserter:")
        assert "job" in snapshot.snapshot
        assert "trigger" in snapshot.snapshot
        assert "target" in snapshot.snapshot
        assert snapshot.snapshot["job"]["id"] == "job_notion_place_inserter"
        assert len(snapshot.snapshot["job"]["stages"]) >= 2
        assert snapshot.snapshot["trigger"]["id"] == "trigger_http_locations"
        assert snapshot.snapshot["target"]["id"] == "target_places_to_visit"
        assert snapshot.snapshot["active_schema"] is None


def test_job_definition_service_returns_none_when_target_missing():
    """JobDefinitionService returns None when target cannot be resolved."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        (Path(base) / "bootstrap" / "jobs").mkdir(parents=True)
        (Path(base) / "bootstrap" / "triggers").mkdir(parents=True)
        (Path(base) / "tenants" / "user_1" / "targets").mkdir(parents=True)

        job_data = load_yaml_file(
            "product_model/bootstrap/jobs/notion_place_inserter.yaml"
        )
        trigger_data = load_yaml_file(
            "product_model/bootstrap/triggers/trigger_http_locations.yaml"
        )
        assert job_data is not None
        assert trigger_data is not None

        from app.repositories.yaml_loader import dump_yaml_file

        dump_yaml_file(
            f"{base}/bootstrap/jobs/notion_place_inserter.yaml",
            job_data,
        )
        dump_yaml_file(
            f"{base}/bootstrap/triggers/trigger_http_locations.yaml",
            trigger_data,
        )

        # No target_places_to_visit in tenant
        job_repo = YamlJobRepository(base=base)
        trigger_repo = YamlTriggerRepository(base=base)
        target_repo = YamlTargetRepository(base=base)
        schema_repo = YamlTargetSchemaRepository(base=base)
        trigger_service = TriggerService(trigger_repository=trigger_repo)
        target_service = TargetService(
            target_repository=target_repo,
            target_schema_repository=schema_repo,
        )
        service = JobDefinitionService(
            job_repository=job_repo,
            trigger_service=trigger_service,
            target_service=target_service,
        )

        snapshot = service.resolve_for_run(
            "job_notion_place_inserter", "user_1", "trigger_http_locations"
        )
        assert snapshot is None


def test_job_definition_service_returns_none_when_job_missing():
    """JobDefinitionService returns None when job cannot be resolved."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        (Path(base) / "tenants" / "user_1" / "targets").mkdir(parents=True)

        job_repo = YamlJobRepository(base=base)
        trigger_repo = YamlTriggerRepository(base=base)
        target_repo = YamlTargetRepository(base=base)
        schema_repo = YamlTargetSchemaRepository(base=base)
        trigger_service = TriggerService(trigger_repository=trigger_repo)
        target_service = TargetService(
            target_repository=target_repo,
            target_schema_repository=schema_repo,
        )
        service = JobDefinitionService(
            job_repository=job_repo,
            trigger_service=trigger_service,
            target_service=target_service,
        )

        snapshot = service.resolve_for_run("job_nonexistent", "user_1", "trigger_http_locations")
        assert snapshot is None


def test_job_definition_service_includes_active_schema_when_present():
    """JobDefinitionService snapshot includes active_schema when target has one."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        (Path(base) / "bootstrap" / "jobs").mkdir(parents=True)
        (Path(base) / "bootstrap" / "triggers").mkdir(parents=True)
        (Path(base) / "tenants" / "user_1" / "targets").mkdir(parents=True)
        (Path(base) / "tenants" / "user_1" / "target_schema_snapshots").mkdir(
            parents=True
        )

        job_data = load_yaml_file(
            "product_model/bootstrap/jobs/notion_place_inserter.yaml"
        )
        trigger_data = load_yaml_file(
            "product_model/bootstrap/triggers/trigger_http_locations.yaml"
        )
        assert job_data is not None
        assert trigger_data is not None

        from app.repositories.yaml_loader import dump_yaml_file

        dump_yaml_file(
            f"{base}/bootstrap/jobs/notion_place_inserter.yaml",
            job_data,
        )
        dump_yaml_file(
            f"{base}/bootstrap/triggers/trigger_http_locations.yaml",
            trigger_data,
        )

        target = DataTarget(
            id="target_places_to_visit",
            owner_user_id="user_1",
            target_template_id="notion_database",
            connector_instance_id="conn_1",
            display_name="Places",
            external_target_id="ext_1",
            status="active",
            active_schema_snapshot_id="schema_1",
        )
        schema = TargetSchemaSnapshot(
            id="schema_1",
            owner_user_id="user_1",
            data_target_id="target_places_to_visit",
            version="1",
            fetched_at=datetime.now(timezone.utc),
            is_active=True,
            source_connector_instance_id="conn_1",
            properties=[],
        )
        target_repo = YamlTargetRepository(base=base)
        schema_repo = YamlTargetSchemaRepository(base=base)
        target_repo.save(target)
        schema_repo.save(schema)

        job_repo = YamlJobRepository(base=base)
        trigger_repo = YamlTriggerRepository(base=base)
        trigger_service = TriggerService(trigger_repository=trigger_repo)
        target_service = TargetService(
            target_repository=target_repo,
            target_schema_repository=schema_repo,
        )
        service = JobDefinitionService(
            job_repository=job_repo,
            trigger_service=trigger_service,
            target_service=target_service,
        )

        snapshot = service.resolve_for_run(
            "job_notion_place_inserter", "user_1", "trigger_http_locations"
        )
        assert snapshot is not None
        assert snapshot.snapshot["active_schema"] is not None
        assert snapshot.snapshot["active_schema"]["id"] == "schema_1"


def test_job_definition_service_snapshot_ref_stable_for_same_content():
    """Same snapshot content produces same snapshot_ref."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        (Path(base) / "bootstrap" / "jobs").mkdir(parents=True)
        (Path(base) / "bootstrap" / "triggers").mkdir(parents=True)
        (Path(base) / "tenants" / "user_1" / "targets").mkdir(parents=True)
        (Path(base) / "tenants" / "user_1" / "target_schema_snapshots").mkdir(
            parents=True
        )

        job_data = load_yaml_file(
            "product_model/bootstrap/jobs/notion_place_inserter.yaml"
        )
        trigger_data = load_yaml_file(
            "product_model/bootstrap/triggers/trigger_http_locations.yaml"
        )
        assert job_data is not None
        assert trigger_data is not None

        from app.repositories.yaml_loader import dump_yaml_file

        dump_yaml_file(
            f"{base}/bootstrap/jobs/notion_place_inserter.yaml",
            job_data,
        )
        dump_yaml_file(
            f"{base}/bootstrap/triggers/trigger_http_locations.yaml",
            trigger_data,
        )

        target = DataTarget(
            id="target_places_to_visit",
            owner_user_id="user_1",
            target_template_id="notion_database",
            connector_instance_id="conn_1",
            display_name="Places",
            external_target_id="ext_1",
            status="active",
            active_schema_snapshot_id=None,
        )
        target_repo = YamlTargetRepository(base=base)
        schema_repo = YamlTargetSchemaRepository(base=base)
        target_repo.save(target)

        job_repo = YamlJobRepository(base=base)
        trigger_repo = YamlTriggerRepository(base=base)
        trigger_service = TriggerService(trigger_repository=trigger_repo)
        target_service = TargetService(
            target_repository=target_repo,
            target_schema_repository=schema_repo,
        )
        service = JobDefinitionService(
            job_repository=job_repo,
            trigger_service=trigger_service,
            target_service=target_service,
        )

        snap1 = service.resolve_for_run("job_notion_place_inserter", "user_1", "trigger_http_locations")
        snap2 = service.resolve_for_run("job_notion_place_inserter", "user_1", "trigger_http_locations")
        assert snap1 is not None
        assert snap2 is not None
        assert snap1.snapshot_ref == snap2.snapshot_ref
