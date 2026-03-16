"""Trigger definitions for Phase 3 domain model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class TriggerDefinition:
    """HTTP trigger definition (V1 supports POST only)."""

    id: str
    owner_user_id: str
    trigger_type: str
    display_name: str
    path: str
    method: str
    request_body_schema: dict[str, Any]
    status: str
    auth_mode: str
    secret_value: str
    secret_last_rotated_at: datetime | None = None
    workspace_id: str | None = None
    visibility: str = "owner"
    created_at: datetime | None = None
    updated_at: datetime | None = None
