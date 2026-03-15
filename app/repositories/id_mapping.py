"""ID mapping registry for nested run IDs. Write-once lookup; never overwrite.

Mapper version and namespace are FROZEN - do not change after deployment.
"""

from __future__ import annotations

import uuid
from typing import Literal

from loguru import logger
from supabase import Client

# FROZEN: Do not change namespace or version after first deployment.
# Changing these will break historical row resolution.
_MAPPER_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-4789-a012-3456789abcde")
_MAPPER_VERSION = "v1"

EntityType = Literal["stage_run", "pipeline_run", "step_run", "usage_record"]
TABLE = "id_mappings"


def _compute_uuid(entity_type: str, source_id: str) -> uuid.UUID:
    """Deterministic UUIDv5 from entity_type:source_id. FROZEN algorithm."""
    name = f"{entity_type}:{source_id}"
    return uuid.uuid5(_MAPPER_NAMESPACE, name)


def resolve_or_create_mapping(
    client: Client,
    entity_type: EntityType,
    source_id: str,
) -> uuid.UUID:
    """
    Resolve source_id to mapped_uuid. Lookup in id_mappings first; if absent,
    compute UUID, insert mapping, return. Never overwrite existing mappings.
    """
    try:
        r = (
            client.table(TABLE)
            .select("mapped_uuid")
            .eq("entity_type", entity_type)
            .eq("source_id", source_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if rows:
            return uuid.UUID(str(rows[0]["mapped_uuid"]))
    except Exception as e:
        logger.exception(
            "id_mapping_lookup_failed | entity_type={} source_id={} error={}",
            entity_type,
            source_id,
            e,
        )
        raise

    mapped = _compute_uuid(entity_type, source_id)
    try:
        client.table(TABLE).insert(
            {
                "entity_type": entity_type,
                "source_id": source_id,
                "mapped_uuid": str(mapped),
                "mapper_version": _MAPPER_VERSION,
            }
        ).execute()
    except Exception as e:
        # Race: another insert may have succeeded; retry lookup
        r = (
            client.table(TABLE)
            .select("mapped_uuid")
            .eq("entity_type", entity_type)
            .eq("source_id", source_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if rows:
            return uuid.UUID(str(rows[0]["mapped_uuid"]))
        logger.exception(
            "id_mapping_insert_failed | entity_type={} source_id={} error={}",
            entity_type,
            source_id,
            e,
        )
        raise
    return mapped


def verify_mapping_consistency(client: Client, sample_size: int = 5) -> None:
    """
    Startup guard: verify that recomputed UUIDs match stored mappings.
    Raises RuntimeError if mismatch detected.
    """
    try:
        r = (
            client.table(TABLE)
            .select("entity_type, source_id, mapped_uuid")
            .eq("mapper_version", _MAPPER_VERSION)
            .limit(sample_size)
            .execute()
        )
        rows = r.data or []
        for row in rows:
            entity_type = row["entity_type"]
            source_id = row["source_id"]
            stored = uuid.UUID(str(row["mapped_uuid"]))
            computed = _compute_uuid(entity_type, source_id)
            if stored != computed:
                raise RuntimeError(
                    f"id_mapping_mismatch: entity_type={entity_type} source_id={source_id} "
                    f"stored={stored} computed={computed}"
                )
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning("id_mapping_verify_skipped | error={}", e)
