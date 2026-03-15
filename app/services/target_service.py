"""Target service for Phase 3: CRUD and active schema resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.repositories import TargetRepository, TargetSchemaRepository
    from app.domain.targets import DataTarget, TargetSchemaSnapshot


@dataclass
class TargetWithSchema:
    """Data target with its active schema snapshot resolved."""

    target: DataTarget
    active_schema: TargetSchemaSnapshot | None


class TargetService:
    """Service for target CRUD and active schema resolution. Storage-agnostic."""

    def __init__(
        self,
        target_repository: TargetRepository,
        target_schema_repository: TargetSchemaRepository,
    ) -> None:
        self._target_repo = target_repository
        self._schema_repo = target_schema_repository

    def get_by_id(
        self, target_id: str, owner_user_id: str
    ) -> DataTarget | None:
        """Return target by ID for the given owner."""
        return self._target_repo.get_by_id(target_id, owner_user_id)

    def list_by_owner(self, owner_user_id: str) -> list[DataTarget]:
        """List all targets for the given owner."""
        return self._target_repo.list_by_owner(owner_user_id)

    def save(self, target: DataTarget) -> None:
        """Persist target. Validation is delegated to repository if configured."""
        self._target_repo.save(target)

    def delete(self, target_id: str, owner_user_id: str) -> None:
        """Remove target by ID for the given owner."""
        self._target_repo.delete(target_id, owner_user_id)

    def get_with_active_schema(
        self, target_id: str, owner_user_id: str
    ) -> TargetWithSchema | None:
        """
        Return target with its active schema snapshot resolved.
        Returns None if target does not exist.
        """
        target = self._target_repo.get_by_id(target_id, owner_user_id)
        if target is None:
            return None
        active_schema = None
        if target.active_schema_snapshot_id:
            active_schema = self._schema_repo.get_by_id(
                target.active_schema_snapshot_id, owner_user_id
            )
        elif target.id:
            active_schema = self._schema_repo.get_active_for_target(
                target.id, owner_user_id
            )
        return TargetWithSchema(target=target, active_schema=active_schema)
