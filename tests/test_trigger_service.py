"""Tests for TriggerService (p3_pr07)."""

import asyncio
import tempfile
from pathlib import Path

from app.domain import TriggerDefinition
from app.repositories import YamlTriggerRepository
from app.services.trigger_service import TriggerService


def test_trigger_service_resolve_by_path_bootstrap():
    """TriggerService resolves /locations from bootstrap trigger."""

    async def _run():
        trigger_repo = YamlTriggerRepository()
        service = TriggerService(trigger_repository=trigger_repo)

        trigger = await service.resolve_by_path("/locations", "bootstrap")
        assert trigger is not None
        assert trigger.path == "/locations"
        assert trigger.owner_user_id == "bootstrap"

    asyncio.run(_run())


def test_trigger_service_resolve_by_path_fallback_to_bootstrap():
    """TriggerService falls back to bootstrap when no tenant trigger exists."""

    async def _run():
        trigger_repo = YamlTriggerRepository()
        service = TriggerService(trigger_repository=trigger_repo)

        trigger = await service.resolve_by_path("/locations", "user_123")
        assert trigger is not None
        assert trigger.path == "/locations"

    asyncio.run(_run())


def test_trigger_service_resolve_by_path_tenant_override():
    """TriggerService prefers tenant trigger over bootstrap."""

    async def _run():
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
                auth_mode="bearer",
                secret_value="tenant_secret_123",
            )
            await trigger_repo.save(tenant_trigger)

            trigger = await service.resolve_by_path("/locations", "user_1")
            assert trigger is not None
            assert trigger.owner_user_id == "user_1"
            assert trigger.id == "t_custom"

    asyncio.run(_run())


def test_trigger_service_resolve_by_path_missing():
    """TriggerService returns None for unknown path."""

    async def _run():
        trigger_repo = YamlTriggerRepository()
        service = TriggerService(trigger_repository=trigger_repo)

        trigger = await service.resolve_by_path("/unknown", "bootstrap")
        assert trigger is None

    asyncio.run(_run())


def test_trigger_service_get_by_id():
    """TriggerService get_by_id delegates to repository."""

    async def _run():
        trigger_repo = YamlTriggerRepository()
        service = TriggerService(trigger_repository=trigger_repo)

        trigger = await service.get_by_id("trigger_http_locations", "bootstrap")
        assert trigger is not None
        assert trigger.id == "trigger_http_locations"

    asyncio.run(_run())


def test_trigger_service_list_by_owner():
    """TriggerService list_by_owner returns bootstrap triggers for bootstrap owner."""

    async def _run():
        trigger_repo = YamlTriggerRepository()
        service = TriggerService(trigger_repository=trigger_repo)

        triggers = await service.list_by_owner("bootstrap")
        assert len(triggers) >= 1
        assert any(t.path == "/locations" for t in triggers)

    asyncio.run(_run())
