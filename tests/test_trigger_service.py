"""Tests for TriggerService (p3_pr07)."""

import tempfile
from pathlib import Path

import pytest

from app.domain import TriggerDefinition
from app.repositories import YamlTriggerRepository
from app.repositories.yaml_loader import load_yaml_file
from app.services.trigger_service import TriggerService


def test_trigger_service_resolve_by_path_bootstrap():
    """TriggerService resolves /locations from bootstrap trigger."""
    trigger_repo = YamlTriggerRepository()
    service = TriggerService(trigger_repository=trigger_repo)

    trigger = service.resolve_by_path("/locations", "bootstrap")
    assert trigger is not None
    assert trigger.path == "/locations"
    assert trigger.job_id == "job_notion_place_inserter"
    assert trigger.owner_user_id == "bootstrap"


def test_trigger_service_resolve_by_path_fallback_to_bootstrap():
    """TriggerService falls back to bootstrap when no tenant trigger exists."""
    trigger_repo = YamlTriggerRepository()
    service = TriggerService(trigger_repository=trigger_repo)

    trigger = service.resolve_by_path("/locations", "user_123")
    assert trigger is not None
    assert trigger.path == "/locations"
    assert trigger.job_id == "job_notion_place_inserter"


def test_trigger_service_resolve_by_path_tenant_override():
    """TriggerService prefers tenant trigger over bootstrap."""
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "product_model")
        (Path(base) / "tenants" / "user_1" / "triggers").mkdir(parents=True)
        trigger_repo = YamlTriggerRepository(base=base)
        service = TriggerService(trigger_repository=trigger_repo)

        tenant_trigger = TriggerDefinition(
            id="t_custom",
            owner_user_id="user_1",
            trigger_type="http",
            display_name="Custom",
            path="/locations",
            method="POST",
            request_body_schema={},
            status="active",
            job_id="job_custom",
            auth_mode="bearer",
        )
        trigger_repo.save(tenant_trigger)

        trigger = service.resolve_by_path("/locations", "user_1")
        assert trigger is not None
        assert trigger.job_id == "job_custom"
        assert trigger.owner_user_id == "user_1"


def test_trigger_service_resolve_by_path_missing():
    """TriggerService returns None for unknown path."""
    trigger_repo = YamlTriggerRepository()
    service = TriggerService(trigger_repository=trigger_repo)

    trigger = service.resolve_by_path("/unknown", "bootstrap")
    assert trigger is None


def test_trigger_service_get_by_id():
    """TriggerService get_by_id delegates to repository."""
    trigger_repo = YamlTriggerRepository()
    service = TriggerService(trigger_repository=trigger_repo)

    trigger = service.get_by_id("trigger_http_locations", "bootstrap")
    assert trigger is not None
    assert trigger.id == "trigger_http_locations"


def test_trigger_service_list_by_owner():
    """TriggerService list_by_owner returns bootstrap triggers for bootstrap owner."""
    trigger_repo = YamlTriggerRepository()
    service = TriggerService(trigger_repository=trigger_repo)

    triggers = service.list_by_owner("bootstrap")
    assert len(triggers) >= 1
    assert any(t.path == "/locations" for t in triggers)
