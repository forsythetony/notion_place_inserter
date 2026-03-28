"""Per-process TTL cache for prepared Notion page payloads (worker fast path)."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

def parse_cache_results_enabled(raw: str | None) -> bool:
    """True when CACHE_RESULTS is 1/true/yes/on."""
    if raw is None or raw == "":
        return False
    return raw.strip().lower() in ("1", "true", "yes", "on")


def parse_cache_results_ttl_seconds(raw: str | None, default: float = 300.0) -> float:
    """Parse CACHE_RESULTS_TTL_SECONDS; invalid or empty uses default."""
    if raw is None or str(raw).strip() == "":
        return default
    try:
        v = float(str(raw).strip())
        return v if v > 0 else default
    except ValueError:
        return default


def canonical_json_for_cache(obj: Any) -> str:
    """Deterministic JSON for hashing (sorted keys, stable for nested dicts/lists)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def build_worker_result_cache_key(
    *,
    owner_user_id: str | None,
    definition_snapshot_ref: str | None,
    data_source_id: str,
    trigger_payload: dict[str, Any],
    dry_run: bool,
    invocation_source: str | None,
) -> str:
    """
    Stable key for logical duplicate requests. Excludes per-run ids (run_id, platform job_id).
    """
    payload = {
        "owner_user_id": owner_user_id or "",
        "definition_snapshot_ref": definition_snapshot_ref or "",
        "data_source_id": data_source_id,
        "trigger_payload": trigger_payload,
        "dry_run": dry_run,
        "invocation_source": invocation_source or "",
    }
    canonical = canonical_json_for_cache(payload)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"wrc:{digest}"


@dataclass(frozen=True)
class CachedNotionWritePayload:
    """Prepared inputs for Notion create_page (after pipeline stages)."""

    notion_properties: dict[str, Any]
    icon: dict[str, Any] | None
    cover: dict[str, Any] | None


@dataclass
class _CacheEntry:
    value: CachedNotionWritePayload
    fetched_at: float


class WorkerResultPayloadCache:
    """
    Lazy TTL cache: entries expire on read (no background sweeper).
    Thread-safe for concurrent async worker tasks.
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = Lock()

    def get(self, key: str) -> CachedNotionWritePayload | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if (time.monotonic() - entry.fetched_at) >= self._ttl:
                del self._entries[key]
                return None
            return entry.value

    def set(self, key: str, value: CachedNotionWritePayload) -> None:
        with self._lock:
            self._entries[key] = _CacheEntry(
                value=value,
                fetched_at=time.monotonic(),
            )

    def invalidate(self, key: str | None = None) -> None:
        """Drop one key or clear all (tests / admin hooks)."""
        with self._lock:
            if key:
                self._entries.pop(key, None)
            else:
                self._entries.clear()
