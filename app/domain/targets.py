"""Target templates, data targets, and schema snapshots for Phase 3 domain model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class TargetTemplate:
    """Platform-owned metadata for a target type (e.g. notion_database)."""

    id: str
    slug: str
    display_name: str
    target_kind: str
    required_connector_template_id: str
    supports_schema_snapshots: bool
    property_types_supported: list[str]
    owner_user_id: str | None = None
    workspace_id: str | None = None
    visibility: str = "platform"


@dataclass
class TargetSchemaProperty:
    """Single property within a schema snapshot with stable ID."""

    id: str
    external_property_id: str
    name: str
    normalized_slug: str
    property_type: str
    required: bool = False
    readonly: bool = False
    options: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class TargetSchemaSnapshot:
    """Fetched schema at a point in time for a data target."""

    id: str
    owner_user_id: str
    data_target_id: str
    version: str
    fetched_at: datetime
    is_active: bool
    source_connector_instance_id: str
    properties: list[TargetSchemaProperty]
    workspace_id: str | None = None
    visibility: str = "owner"
    raw_source_payload: dict[str, Any] | None = None


@dataclass
class DataTarget:
    """User-owned global resource representing a specific target instance (e.g. Notion database)."""

    id: str
    owner_user_id: str
    target_template_id: str
    connector_instance_id: str
    display_name: str
    external_target_id: str
    status: str
    workspace_id: str | None = None
    visibility: str = "owner"
    active_schema_snapshot_id: str | None = None
    target_settings: dict[str, Any] | None = None
    property_rules: dict[str, dict[str, Any]] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
