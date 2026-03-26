"""Trigger service for Phase 3: CRUD and path resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.repositories import TriggerRepository
    from app.domain.triggers import TriggerDefinition


class TriggerService:
    """Service for trigger CRUD and resolution by path. Storage-agnostic."""

    def __init__(self, trigger_repository: TriggerRepository) -> None:
        self._repo = trigger_repository

    async def get_by_id(self, id: str, owner_user_id: str) -> TriggerDefinition | None:
        """Return trigger by ID for the given owner."""
        return await self._repo.get_by_id(id, owner_user_id)

    async def get_by_path(self, path: str, owner_user_id: str) -> TriggerDefinition | None:
        """Return trigger by HTTP path for the given owner."""
        return await self._repo.get_by_path(path, owner_user_id)

    async def list_by_owner(self, owner_user_id: str) -> list[TriggerDefinition]:
        """List all triggers for the given owner."""
        return await self._repo.list_by_owner(owner_user_id)

    async def save(self, trigger: TriggerDefinition) -> None:
        """Persist trigger. Validation is delegated to repository if configured."""
        await self._repo.save(trigger)

    async def delete(self, id: str, owner_user_id: str) -> None:
        """Remove trigger by ID for the given owner."""
        await self._repo.delete(id, owner_user_id)

    async def resolve_by_path(
        self, path: str, owner_user_id: str
    ) -> TriggerDefinition | None:
        """
        Resolve trigger by path and owner.
        Repository checks tenant triggers first, then bootstrap dir (shared starter).
        Returns None if no trigger matches.
        """
        return await self._repo.get_by_path(path, owner_user_id)
