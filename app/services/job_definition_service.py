"""Job definition resolution and snapshotting for Phase 3 (p3_pr05)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.repositories.yaml_loader import domain_to_yaml_dict, job_graph_to_yaml_dict

if TYPE_CHECKING:
    from app.domain.repositories import JobRepository
    from app.services.target_service import TargetService
    from app.services.trigger_service import TriggerService


@dataclass(frozen=True)
class ResolvedJobSnapshot:
    """Immutable, self-contained snapshot for execution. Suitable for persistence."""

    snapshot_ref: str
    snapshot: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a defensive copy of the snapshot dict."""
        return _deep_copy_dict(self.snapshot)


def _deep_copy_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Recursively copy dict for immutability at boundary."""
    result: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _deep_copy_dict(v)
        elif isinstance(v, list):
            result[k] = [
                _deep_copy_dict(x) if isinstance(x, dict) else x
                for x in v
            ]
        else:
            result[k] = v
    return result


def _collect_related_target_ids(graph) -> set[str]:
    """Collect unique related_db (data_target_id) from all steps in the job graph."""
    ids: set[str] = set()
    for step in graph.steps:
        related = step.config.get("related_db") if step.config else None
        if isinstance(related, str) and related.strip():
            ids.add(related.strip())
    return ids


def _canonical_hash(snapshot: dict[str, Any]) -> str:
    """Deterministic hash of snapshot for snapshot_ref."""
    canonical = json.dumps(snapshot, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class JobDefinitionService:
    """
    Resolves job definitions into complete, owner-scoped snapshots for execution.
    Snapshots are immutable and self-contained (job, stages, pipelines, steps, trigger, target, schema).
    """

    def __init__(
        self,
        *,
        job_repository: JobRepository,
        trigger_service: TriggerService,
        target_service: TargetService,
    ) -> None:
        self._job_repo = job_repository
        self._trigger_service = trigger_service
        self._target_service = target_service

    def resolve_for_run(
        self, job_id: str, owner_user_id: str
    ) -> ResolvedJobSnapshot | None:
        """
        Resolve a job by ID into a complete snapshot for execution.
        Returns None if job, trigger, or target cannot be resolved for the owner.
        Snapshot is owner-scoped; cross-tenant resolution is rejected.
        """
        job_repo = self._job_repo
        if not hasattr(job_repo, "get_graph_by_id"):
            return None
        graph = job_repo.get_graph_by_id(job_id, owner_user_id)
        if graph is None:
            return None

        job = graph.job
        trigger = self._trigger_service.get_by_id(job.trigger_id, owner_user_id)
        if trigger is None:
            return None

        target_with_schema = self._target_service.get_with_active_schema(
            job.target_id, owner_user_id
        )
        if target_with_schema is None:
            return None

        job_graph_dict = job_graph_to_yaml_dict(graph)
        trigger_dict = domain_to_yaml_dict(trigger)
        target_dict = domain_to_yaml_dict(target_with_schema.target)
        active_schema_dict = (
            domain_to_yaml_dict(target_with_schema.active_schema)
            if target_with_schema.active_schema is not None
            else None
        )

        related_target_ids = _collect_related_target_ids(graph)
        targets_dict: dict[str, Any] = {}
        owner_for_targets = owner_user_id
        for tid in related_target_ids:
            t = self._target_service.get_by_id(tid, owner_for_targets)
            if t is not None:
                targets_dict[tid] = domain_to_yaml_dict(t)

        snapshot: dict[str, Any] = {
            "job": job_graph_dict,
            "trigger": trigger_dict,
            "target": target_dict,
            "active_schema": active_schema_dict,
            "targets": targets_dict,
        }

        snapshot_ref = (
            f"job_snapshot:{owner_user_id}:{job_id}:{_canonical_hash(snapshot)}"
        )
        return ResolvedJobSnapshot(snapshot_ref=snapshot_ref, snapshot=snapshot)
