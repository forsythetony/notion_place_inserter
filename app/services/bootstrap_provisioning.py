"""Bootstrap provisioning interface for runtime idempotent seeding and lazy owner provisioning."""

from __future__ import annotations

from typing import Protocol


class BootstrapProvisioningService(Protocol):
    """
    Interface for bootstrap/seed operations. Segregated so removal is a single wiring change.
    No direct YAML parsing from routes, worker loop, or repository classes.
    """

    def seed_catalog_if_needed(self) -> None:
        """Idempotently seed platform catalog (connector_templates, target_templates, step_templates)."""

    def ensure_owner_starter_definitions(self, owner_user_id: str) -> None:
        """
        Ensure owner has starter definitions (connector instances, target, trigger, job graph).
        Called on first trigger invocation for a user. Idempotent.
        """

    def reprovision_owner_starter_definitions(self, owner_user_id: str) -> None:
        """
        Replace starter job + ``/locations`` trigger from bundled YAML (destructive).
        Optional: only implemented by Postgres bootstrap provisioning.
        """
