"""Connector templates and instances for Phase 3 domain model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ConnectorTemplate:
    """Platform-owned marketplace entry for a connector type."""

    id: str
    slug: str
    display_name: str
    connector_type: str
    provider: str
    auth_strategy: str
    capabilities: list[str]
    config_schema: dict[str, Any]
    secret_schema: dict[str, Any]
    status: str
    owner_user_id: str | None = None
    workspace_id: str | None = None
    visibility: str = "platform"


@dataclass
class ConnectorInstance:
    """User-owned configured connector instance."""

    id: str
    owner_user_id: str
    connector_template_id: str
    display_name: str
    status: str
    config: dict[str, Any]
    secret_ref: str | None
    workspace_id: str | None = None
    visibility: str = "owner"
    last_validated_at: datetime | None = None
    last_error: str | None = None
