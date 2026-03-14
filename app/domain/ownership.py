"""Ownership and visibility primitives for Phase 3 domain model."""

from typing import Literal

Visibility = Literal["platform", "owner"]
"""Visibility of a persisted object: platform (marketplace) or owner (tenant-scoped)."""
