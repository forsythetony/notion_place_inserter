"""Schema sync service: fetch live schema from connector, create snapshot, attach to target."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.domain.targets import TargetSchemaProperty, TargetSchemaSnapshot

if TYPE_CHECKING:
    from app.domain.connectors import ConnectorInstance
    from app.domain.repositories import (
        ConnectorInstanceRepository,
        TargetRepository,
        TargetSchemaRepository,
    )
    from app.domain.targets import DataTarget
    from app.services.notion_service import NotionService

_PLAINTEXT_SECRET_KEYS = frozenset(
    {"api_key", "secret", "token", "password", "auth_token", "access_token"}
)


def _has_plaintext_secrets(config: dict[str, Any]) -> bool:
    """Return True if config contains plaintext secret-like values."""
    for key in _PLAINTEXT_SECRET_KEYS:
        val = config.get(key)
        if isinstance(val, str) and val.strip():
            return True
        if isinstance(val, dict) and val:
            return True
    return False


def _notion_raw_property_to_target_schema_property(
    prop_name: str, raw: dict[str, Any]
) -> TargetSchemaProperty:
    """Map Notion raw property to TargetSchemaProperty."""
    prop_id = raw.get("id", prop_name)
    prop_type = raw.get("type", "unknown")
    normalized = prop_name.lower().replace(" ", "_").replace("-", "_")
    options = None
    if prop_type in ("select", "multi_select"):
        opts = raw.get(prop_type, {}).get("options", [])
        options = [
            {"id": o.get("id", ""), "name": o.get("name", ""), "color": o.get("color", "")}
            for o in opts
        ]
    return TargetSchemaProperty(
        id=f"prop_{normalized}",
        external_property_id=prop_id,
        name=prop_name,
        normalized_slug=normalized,
        property_type=prop_type,
        required=False,
        readonly=False,
        options=options,
        metadata=None,
    )


class SchemaSyncServiceError(Exception):
    """Raised when schema sync fails (e.g. secret_ref violation, target not found)."""

    pass


class SchemaSyncService:
    """Fetches live schema from connector, creates TargetSchemaSnapshot, attaches to DataTarget."""

    def __init__(
        self,
        target_repository: TargetRepository,
        target_schema_repository: TargetSchemaRepository,
        connector_instance_repository: ConnectorInstanceRepository,
        notion_service: NotionService | None = None,
    ) -> None:
        self._target_repo = target_repository
        self._schema_repo = target_schema_repository
        self._connector_repo = connector_instance_repository
        self._notion_service = notion_service

    def _ensure_secret_ref_only(self, instance: ConnectorInstance) -> None:
        """Raise SchemaSyncServiceError if connector uses plaintext secrets."""
        if _has_plaintext_secrets(instance.config):
            raise SchemaSyncServiceError(
                f"Connector instance '{instance.id}' must use secret_ref, not plaintext secrets"
            )
        if not instance.secret_ref or not str(instance.secret_ref).strip():
            raise SchemaSyncServiceError(
                f"Connector instance '{instance.id}' must have secret_ref set"
            )

    def sync_for_target(
        self, data_target_id: str, owner_user_id: str
    ) -> TargetSchemaSnapshot:
        """
        Fetch live schema for target, create snapshot, attach to target.
        For notion_database targets, uses NotionService. Enforces secret_ref on connector.
        """
        target = self._target_repo.get_by_id(data_target_id, owner_user_id)
        if target is None:
            raise SchemaSyncServiceError(
                f"Target '{data_target_id}' not found for owner '{owner_user_id}'"
            )

        connector = self._connector_repo.get_by_id(
            target.connector_instance_id, owner_user_id
        )
        if connector is None:
            raise SchemaSyncServiceError(
                f"Connector instance '{target.connector_instance_id}' not found"
            )

        self._ensure_secret_ref_only(connector)

        # Notion path: use display_name as db_name
        if target.target_template_id == "notion_database" and self._notion_service:
            return self._sync_notion_target(target, owner_user_id)

        raise SchemaSyncServiceError(
            f"Schema sync not supported for target template '{target.target_template_id}'"
        )

    def _sync_notion_target(
        self, target: DataTarget, owner_user_id: str
    ) -> TargetSchemaSnapshot:
        """Fetch schema from Notion, create snapshot, attach to target."""
        db_name = target.display_name or target.external_target_id or ""
        if not db_name.strip():
            raise SchemaSyncServiceError(
                f"Target '{target.id}' has no display_name or external_target_id for Notion lookup"
            )

        data_source_id, raw_props = self._notion_service.get_raw_schema_for_sync(
            db_name
        )

        # Deactivate previous active snapshot for this target
        for snap in self._schema_repo.list_by_owner(owner_user_id):
            if snap.data_target_id == target.id and snap.is_active:
                from dataclasses import replace

                deactivated = replace(snap, is_active=False)
                self._schema_repo.save(deactivated)
                break

        # Build snapshot
        snapshot_id = f"schema_{target.id}_{uuid.uuid4().hex[:8]}"
        properties: list[TargetSchemaProperty] = []
        for prop_name, raw in raw_props.items():
            if isinstance(raw, dict):
                try:
                    properties.append(
                        _notion_raw_property_to_target_schema_property(
                            prop_name, raw
                        )
                    )
                except Exception as e:
                    logger.warning(
                        "schema_sync_skip_property | target={} prop={} error={}",
                        target.id,
                        prop_name,
                        e,
                    )

        snapshot = TargetSchemaSnapshot(
            id=snapshot_id,
            owner_user_id=owner_user_id,
            data_target_id=target.id,
            version="1",
            fetched_at=datetime.now(timezone.utc),
            is_active=True,
            source_connector_instance_id=target.connector_instance_id,
            properties=properties,
            workspace_id=target.workspace_id,
            visibility="owner",
            raw_source_payload={"data_source_id": data_source_id},
        )
        self._schema_repo.save(snapshot)

        # Update target
        from dataclasses import replace

        updated_target = replace(
            target, active_schema_snapshot_id=snapshot_id
        )
        self._target_repo.save(updated_target)

        logger.info(
            "schema_sync_completed | target_id={} snapshot_id={} property_count={}",
            target.id,
            snapshot_id,
            len(properties),
        )
        return snapshot
