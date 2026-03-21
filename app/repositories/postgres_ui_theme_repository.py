"""Postgres-backed UI theme presets and active pointer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from loguru import logger
from supabase import Client


def _parse_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    return None


def _coerce_config(val: Any) -> dict[str, Any]:
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


class PostgresUiThemeRepository:
    """CRUD for ui_theme_presets and app_ui_theme_settings singleton."""

    TABLE_PRESETS = "ui_theme_presets"
    TABLE_SETTINGS = "app_ui_theme_settings"
    SETTINGS_PK = 1

    def __init__(self, client: Client) -> None:
        self._client = client

    def list_presets_metadata(self) -> list[dict[str, Any]]:
        """List presets with id, name, is_system, updated_at (no config)."""
        r = (
            self._client.table(self.TABLE_PRESETS)
            .select("id, name, is_system, updated_at")
            .order("updated_at", desc=True)
            .execute()
        )
        rows = r.data or []
        out = []
        for row in rows:
            out.append(
                {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "is_system": bool(row.get("is_system", False)),
                    "updated_at": _parse_dt(row.get("updated_at")),
                }
            )
        return out

    def get_preset_by_id(self, preset_id: str) -> dict[str, Any] | None:
        r = (
            self._client.table(self.TABLE_PRESETS)
            .select("*")
            .eq("id", preset_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            return None
        row = rows[0]
        return self._row_to_preset(row)

    def _row_to_preset(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "name": row["name"],
            "config": _coerce_config(row.get("config")),
            "is_system": bool(row.get("is_system", False)),
            "created_at": _parse_dt(row.get("created_at")),
            "updated_at": _parse_dt(row.get("updated_at")),
            "created_by_user_id": str(row["created_by_user_id"])
            if row.get("created_by_user_id")
            else None,
        }

    def create_preset(
        self,
        name: str,
        config: dict[str, Any],
        *,
        is_system: bool = False,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        new_id = str(uuid4())
        row: dict[str, Any] = {
            "id": new_id,
            "name": name,
            "config": config,
            "is_system": is_system,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if created_by_user_id:
            row["created_by_user_id"] = created_by_user_id
        # postgrest-py: neither insert().select() nor update().select() — use explicit id + fetch after write.
        self._client.table(self.TABLE_PRESETS).insert(row).execute()
        loaded = self.get_preset_by_id(new_id)
        if not loaded:
            logger.error("ui_theme_preset_insert_fetch_failed | id={}", new_id)
            raise RuntimeError("ui_theme_preset_insert_failed")
        return loaded

    def update_preset(
        self,
        preset_id: str,
        *,
        name: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if name is not None:
            updates["name"] = name
        if config is not None:
            updates["config"] = config
        self._client.table(self.TABLE_PRESETS).update(updates).eq("id", preset_id).execute()
        return self.get_preset_by_id(preset_id)

    def delete_preset(self, preset_id: str) -> bool:
        r = self._client.table(self.TABLE_PRESETS).delete().eq("id", preset_id).execute()
        rows = r.data or []
        return len(rows) > 0

    def get_preset_is_system(self, preset_id: str) -> bool | None:
        r = (
            self._client.table(self.TABLE_PRESETS)
            .select("is_system")
            .eq("id", preset_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            return None
        return bool(rows[0].get("is_system", False))

    def get_active_preset_id(self) -> str | None:
        r = (
            self._client.table(self.TABLE_SETTINGS)
            .select("active_preset_id")
            .eq("id", self.SETTINGS_PK)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            return None
        aid = rows[0].get("active_preset_id")
        return str(aid) if aid else None

    def set_active_preset_id(self, preset_id: str | None) -> None:
        self._client.table(self.TABLE_SETTINGS).update(
            {
                "active_preset_id": preset_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", self.SETTINGS_PK).execute()

    def duplicate_preset(
        self,
        source_id: str,
        name: str | None,
        *,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any] | None:
        src = self.get_preset_by_id(source_id)
        if not src:
            return None
        new_name = (name or "").strip() or f"{src['name']} (copy)"
        return self.create_preset(
            new_name,
            src["config"],
            is_system=False,
            created_by_user_id=created_by_user_id,
        )
