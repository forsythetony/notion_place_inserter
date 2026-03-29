"""Postgres-backed repository implementations for Phase 4 datastore."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from loguru import logger
from supabase import AsyncClient

from app.domain import (
    AppLimits,
    ConnectorInstance,
    ConnectorTemplate,
    DataTarget,
    JobDefinition,
    StepTemplate,
    TargetSchemaProperty,
    TargetSchemaSnapshot,
    TargetTemplate,
    TriggerDefinition,
)
from app.domain.errors import validate_one_trigger_per_job_attach
from app.domain.jobs import PipelineDefinition, StageDefinition, StepInstance
from app.services.validation_service import JobGraph, ValidationService


def _ensure_uuid(owner_user_id: str) -> UUID:
    """Parse owner_user_id to UUID. Raises ValueError if invalid."""
    if isinstance(owner_user_id, UUID):
        return owner_user_id
    return UUID(str(owner_user_id))


def _seq_int(seq: int | float) -> int:
    """Coerce sequence to int for Postgres (schema expects integer)."""
    return int(round(seq)) if isinstance(seq, float) else int(seq)


# Band used only during save_job_graph: move steps here before assigning final 1..n so
# reorders never transiently violate uq_step_sequence_per_pipeline (Postgres checks each row).
_STEP_SEQUENCE_TEMP_BASE = 10_000_000


def _step_instance_row(step: StepInstance, pipeline_id: str, uid: str, sequence: int) -> dict[str, Any]:
    return {
        "id": step.id,
        "pipeline_id": pipeline_id,
        "owner_user_id": uid,
        "step_template_id": step.step_template_id,
        "display_name": step.display_name,
        "sequence": _seq_int(sequence),
        "input_bindings": step.input_bindings,
        "config": step.config,
        "failure_policy": step.failure_policy,
    }


def _row_to_connector_template(row: dict[str, Any]) -> ConnectorTemplate:
    return ConnectorTemplate(
        id=row["id"],
        slug=row["slug"],
        display_name=row["display_name"],
        connector_type=row["connector_type"],
        provider=row["provider"],
        auth_strategy=row["auth_strategy"],
        capabilities=row.get("capabilities") or [],
        config_schema=row.get("config_schema") or {},
        secret_schema=row.get("secret_schema") or {},
        status=str(row.get("status", "active")),
        visibility=str(row.get("visibility", "platform")),
    )


def _row_to_target_template(row: dict[str, Any]) -> TargetTemplate:
    return TargetTemplate(
        id=row["id"],
        slug=row["slug"],
        display_name=row["display_name"],
        target_kind=row["target_kind"],
        required_connector_template_id=row["required_connector_template_id"],
        supports_schema_snapshots=row.get("supports_schema_snapshots", True),
        property_types_supported=row.get("property_types_supported") or [],
        visibility=str(row.get("visibility", "platform")),
    )


def _row_to_step_template(row: dict[str, Any]) -> StepTemplate:
    return StepTemplate(
        id=row["id"],
        slug=row["slug"],
        display_name=row["display_name"],
        step_kind=row["step_kind"],
        description=row.get("description") or "",
        input_contract=row.get("input_contract") or {},
        output_contract=row.get("output_contract") or {},
        config_schema=row.get("config_schema") or {},
        runtime_binding=row.get("runtime_binding") or "",
        category=row.get("category") or "general",
        status=str(row.get("status", "active")),
        visibility=str(row.get("visibility", "platform")),
        query_schema=row.get("query_schema"),
    )


def _parse_opt_datetime(val: Any) -> datetime | None:
    """Parse datetime from row value. Returns None if invalid or missing."""
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


def _row_to_connector_instance(row: dict[str, Any], owner: str) -> ConnectorInstance:
    return ConnectorInstance(
        id=row["id"],
        owner_user_id=owner,
        connector_template_id=row["connector_template_id"],
        display_name=row["display_name"],
        status=str(row.get("status", "active")),
        config=row.get("config") or {},
        secret_ref=row.get("secret_ref"),
        visibility=str(row.get("visibility", "owner")),
        last_validated_at=_parse_opt_datetime(row.get("last_validated_at")),
        last_error=row.get("last_error"),
        auth_status=str(row.get("auth_status", "pending")),
        authorized_at=_parse_opt_datetime(row.get("authorized_at")),
        disconnected_at=_parse_opt_datetime(row.get("disconnected_at")),
        provider_account_id=row.get("provider_account_id"),
        provider_account_name=row.get("provider_account_name"),
        last_synced_at=_parse_opt_datetime(row.get("last_synced_at")),
        metadata=row.get("metadata") or {},
    )


def _row_to_data_target(row: dict[str, Any], owner: str) -> DataTarget:
    return DataTarget(
        id=row["id"],
        owner_user_id=owner,
        target_template_id=row["target_template_id"],
        connector_instance_id=row["connector_instance_id"],
        display_name=row["display_name"],
        external_target_id=row["external_target_id"],
        status=str(row.get("status", "active")),
        active_schema_snapshot_id=row.get("active_schema_snapshot_id"),
        target_settings=row.get("target_settings"),
        property_rules=row.get("property_rules"),
        visibility=str(row.get("visibility", "owner")),
    )


def _row_to_target_schema_snapshot(row: dict[str, Any], owner: str) -> TargetSchemaSnapshot:
    fetched = row.get("fetched_at")
    if isinstance(fetched, str):
        fetched = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
    elif fetched is None:
        fetched = datetime.now(timezone.utc)
    props_raw = row.get("properties") or []
    properties = []
    for p in props_raw:
        if isinstance(p, dict) and p.get("id"):
            properties.append(
                TargetSchemaProperty(
                    id=p["id"],
                    external_property_id=p.get("external_property_id", p["id"]),
                    name=p.get("name", ""),
                    normalized_slug=p.get("normalized_slug", p.get("name", "").lower().replace(" ", "_")),
                    property_type=p.get("property_type", "rich_text"),
                    required=p.get("required", False),
                    readonly=p.get("readonly", False),
                    options=p.get("options"),
                    metadata=p.get("metadata"),
                )
            )
    return TargetSchemaSnapshot(
        id=row["id"],
        owner_user_id=owner,
        data_target_id=row["data_target_id"],
        version=row.get("version", "1"),
        fetched_at=fetched,
        is_active=row.get("is_active", True),
        source_connector_instance_id=row["source_connector_instance_id"],
        properties=properties,
        raw_source_payload=row.get("raw_source_payload"),
        visibility=str(row.get("visibility", "owner")),
    )


def _row_to_trigger(row: dict[str, Any], owner: str) -> TriggerDefinition:
    secret_rotated = row.get("secret_last_rotated_at")
    if isinstance(secret_rotated, str):
        try:
            secret_rotated = datetime.fromisoformat(secret_rotated.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            secret_rotated = None
    return TriggerDefinition(
        id=row["id"],
        owner_user_id=owner,
        trigger_type=row.get("trigger_type", "http"),
        display_name=row["display_name"],
        path=row["path"],
        method=row.get("method", "POST"),
        request_body_schema=row.get("request_body_schema") or {},
        status=str(row.get("status", "active")),
        auth_mode=row.get("auth_mode", "bearer"),
        secret_value=row.get("secret_value", ""),
        secret_last_rotated_at=secret_rotated,
        visibility=str(row.get("visibility", "owner")),
    )


def _row_to_job(row: dict[str, Any], owner: str) -> JobDefinition:
    stage_ids = row.get("stage_ids") or []
    if isinstance(stage_ids, str):
        stage_ids = []
    return JobDefinition(
        id=row["id"],
        owner_user_id=owner,
        display_name=row["display_name"],
        target_id=row["target_id"],
        status=str(row.get("status", "active")),
        stage_ids=stage_ids,
        default_run_settings=row.get("default_run_settings"),
        visibility=str(row.get("visibility", "owner")),
        created_at=_parse_opt_datetime(row.get("created_at")),
        updated_at=_parse_opt_datetime(row.get("updated_at")),
    )


def _row_to_step_instance(row: dict[str, Any], pipeline_id: str, owner: str) -> StepInstance:
    return StepInstance(
        id=row["id"],
        pipeline_id=pipeline_id,
        step_template_id=row["step_template_id"],
        display_name=row.get("display_name") or row["id"],
        sequence=row.get("sequence", 0),
        input_bindings=row.get("input_bindings") or {},
        config=row.get("config") or {},
        failure_policy=row.get("failure_policy"),
    )


def _row_to_pipeline(row: dict[str, Any], stage_id: str, owner: str) -> PipelineDefinition:
    step_ids = row.get("step_ids") or []
    if isinstance(step_ids, str):
        step_ids = []
    return PipelineDefinition(
        id=row["id"],
        stage_id=stage_id,
        display_name=row.get("display_name") or row["id"],
        sequence=row.get("sequence", 0),
        step_ids=step_ids,
        purpose=row.get("purpose"),
    )


def _row_to_stage(row: dict[str, Any], job_id: str, owner: str) -> StageDefinition:
    pipeline_ids = row.get("pipeline_ids") or []
    if isinstance(pipeline_ids, str):
        pipeline_ids = []
    return StageDefinition(
        id=row["id"],
        job_id=job_id,
        display_name=row.get("display_name") or row["id"],
        sequence=row.get("sequence", 0),
        pipeline_ids=pipeline_ids,
        pipeline_run_mode=row.get("pipeline_run_mode", "parallel"),
    )


class PostgresConnectorTemplateRepository:
    """Postgres-backed connector template catalog."""

    TABLE = "connector_templates"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_by_id(self, id: str) -> ConnectorTemplate | None:
        try:
            r = await self._client.table(self.TABLE).select("*").eq("id", id).limit(1).execute()
        except Exception as e:
            logger.exception("postgres_connector_template_get_failed | id={} error={}", id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_connector_template(rows[0])

    async def list_all(self) -> list[ConnectorTemplate]:
        try:
            r = await self._client.table(self.TABLE).select("*").execute()
        except Exception as e:
            logger.exception("postgres_connector_template_list_failed | error={}", e)
            raise
        return [_row_to_connector_template(row) for row in (r.data or [])]

    async def save(self, template: ConnectorTemplate) -> None:
        row = {
            "id": template.id,
            "slug": template.slug,
            "display_name": template.display_name,
            "connector_type": template.connector_type,
            "provider": template.provider,
            "auth_strategy": template.auth_strategy,
            "capabilities": template.capabilities,
            "config_schema": template.config_schema,
            "secret_schema": template.secret_schema,
            "status": template.status,
            "visibility": template.visibility,
        }
        try:
            await self._client.table(self.TABLE).upsert(row, on_conflict="id").execute()
        except Exception as e:
            logger.exception("postgres_connector_template_save_failed | id={} error={}", template.id, e)
            raise

    async def delete(self, id: str) -> None:
        try:
            await self._client.table(self.TABLE).delete().eq("id", id).execute()
        except Exception as e:
            logger.exception("postgres_connector_template_delete_failed | id={} error={}", id, e)
            raise


class PostgresTargetTemplateRepository:
    """Postgres-backed target template catalog."""

    TABLE = "target_templates"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_by_id(self, id: str) -> TargetTemplate | None:
        try:
            r = await self._client.table(self.TABLE).select("*").eq("id", id).limit(1).execute()
        except Exception as e:
            logger.exception("postgres_target_template_get_failed | id={} error={}", id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_target_template(rows[0])

    async def list_all(self) -> list[TargetTemplate]:
        try:
            r = await self._client.table(self.TABLE).select("*").execute()
        except Exception as e:
            logger.exception("postgres_target_template_list_failed | error={}", e)
            raise
        return [_row_to_target_template(row) for row in (r.data or [])]

    async def save(self, template: TargetTemplate) -> None:
        row = {
            "id": template.id,
            "slug": template.slug,
            "display_name": template.display_name,
            "target_kind": template.target_kind,
            "required_connector_template_id": template.required_connector_template_id,
            "supports_schema_snapshots": template.supports_schema_snapshots,
            "property_types_supported": template.property_types_supported,
            "status": "active",
            "visibility": template.visibility,
        }
        try:
            await self._client.table(self.TABLE).upsert(row, on_conflict="id").execute()
        except Exception as e:
            logger.exception("postgres_target_template_save_failed | id={} error={}", template.id, e)
            raise

    async def delete(self, id: str) -> None:
        try:
            await self._client.table(self.TABLE).delete().eq("id", id).execute()
        except Exception as e:
            logger.exception("postgres_target_template_delete_failed | id={} error={}", id, e)
            raise


class PostgresStepTemplateRepository:
    """Postgres-backed step template catalog."""

    TABLE = "step_templates"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_by_id(self, id: str) -> StepTemplate | None:
        try:
            r = await self._client.table(self.TABLE).select("*").eq("id", id).limit(1).execute()
        except Exception as e:
            logger.exception("postgres_step_template_get_failed | id={} error={}", id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_step_template(rows[0])

    async def list_all(self) -> list[StepTemplate]:
        try:
            r = await self._client.table(self.TABLE).select("*").execute()
        except Exception as e:
            logger.exception("postgres_step_template_list_failed | error={}", e)
            raise
        return [_row_to_step_template(row) for row in (r.data or [])]

    async def save(self, template: StepTemplate) -> None:
        row = {
            "id": template.id,
            "slug": template.slug,
            "display_name": template.display_name,
            "step_kind": template.step_kind,
            "description": template.description,
            "input_contract": template.input_contract,
            "output_contract": template.output_contract,
            "config_schema": template.config_schema,
            "runtime_binding": template.runtime_binding,
            "category": template.category,
            "status": template.status,
            "visibility": template.visibility,
            "query_schema": template.query_schema,
        }
        try:
            await self._client.table(self.TABLE).upsert(row, on_conflict="id").execute()
        except Exception as e:
            logger.exception("postgres_step_template_save_failed | id={} error={}", template.id, e)
            raise

    async def delete(self, id: str) -> None:
        try:
            await self._client.table(self.TABLE).delete().eq("id", id).execute()
        except Exception as e:
            logger.exception("postgres_step_template_delete_failed | id={} error={}", id, e)
            raise


class PostgresConnectorInstanceRepository:
    """Postgres-backed connector instance repository."""

    TABLE = "connector_instances"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_by_id(self, id: str, owner_user_id: str) -> ConnectorInstance | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await self._client.table(self.TABLE).select("*").eq("id", id).eq("owner_user_id", uid).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_connector_instance_get_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_connector_instance(rows[0], owner_user_id)

    async def list_by_owner(self, owner_user_id: str) -> list[ConnectorInstance]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).execute()
        except ValueError:
            return []
        except Exception as e:
            logger.exception("postgres_connector_instance_list_failed | owner={} error={}", owner_user_id, e)
            raise
        return [_row_to_connector_instance(row, owner_user_id) for row in (r.data or [])]

    async def save(self, instance: ConnectorInstance) -> None:
        uid = str(_ensure_uuid(instance.owner_user_id))
        row = {
            "id": instance.id,
            "owner_user_id": uid,
            "connector_template_id": instance.connector_template_id,
            "display_name": instance.display_name,
            "status": instance.status,
            "config": instance.config,
            "secret_ref": instance.secret_ref,
            "visibility": instance.visibility,
            "last_validated_at": instance.last_validated_at.isoformat() if instance.last_validated_at else None,
            "last_error": instance.last_error,
            "auth_status": instance.auth_status,
            "authorized_at": instance.authorized_at.isoformat() if instance.authorized_at else None,
            "disconnected_at": instance.disconnected_at.isoformat() if instance.disconnected_at else None,
            "provider_account_id": instance.provider_account_id,
            "provider_account_name": instance.provider_account_name,
            "last_synced_at": instance.last_synced_at.isoformat() if instance.last_synced_at else None,
            "metadata": instance.metadata or {},
        }
        try:
            await self._client.table(self.TABLE).upsert(row, on_conflict="id,owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_connector_instance_save_failed | id={} error={}", instance.id, e)
            raise

    async def delete(self, id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            await self._client.table(self.TABLE).delete().eq("id", id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception("postgres_connector_instance_delete_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise


class PostgresTargetRepository:
    """Postgres-backed data target repository."""

    TABLE = "data_targets"

    def __init__(
        self,
        client: AsyncClient,
        validation_service: ValidationService | None = None,
    ) -> None:
        self._client = client
        self._validation_service = validation_service

    def set_validation_service(self, validation_service: ValidationService | None) -> None:
        self._validation_service = validation_service

    async def get_by_id(self, id: str, owner_user_id: str) -> DataTarget | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await self._client.table(self.TABLE).select("*").eq("id", id).eq("owner_user_id", uid).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_target_get_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_data_target(rows[0], owner_user_id)

    async def list_by_owner(self, owner_user_id: str) -> list[DataTarget]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).execute()
        except ValueError:
            return []
        except Exception as e:
            logger.exception("postgres_target_list_failed | owner={} error={}", owner_user_id, e)
            raise
        return [_row_to_data_target(row, owner_user_id) for row in (r.data or [])]

    async def list_by_connector(
        self, connector_instance_id: str, owner_user_id: str
    ) -> list[DataTarget]:
        """List data targets for a connector instance (e.g. Notion)."""
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await (
                self._client.table(self.TABLE)
                .select("*")
                .eq("owner_user_id", uid)
                .eq("connector_instance_id", connector_instance_id)
                .execute()
            )
        except ValueError:
            return []
        except Exception as e:
            logger.exception(
                "postgres_target_list_by_connector_failed | connector={} owner={} error={}",
                connector_instance_id,
                owner_user_id,
                e,
            )
            raise
        return [_row_to_data_target(row, owner_user_id) for row in (r.data or [])]

    async def save(self, target: DataTarget) -> None:
        if self._validation_service:
            await self._validation_service.validate_data_target(target)
        uid = str(_ensure_uuid(target.owner_user_id))
        row = {
            "id": target.id,
            "owner_user_id": uid,
            "target_template_id": target.target_template_id,
            "connector_instance_id": target.connector_instance_id,
            "display_name": target.display_name,
            "external_target_id": target.external_target_id,
            "status": target.status,
            "active_schema_snapshot_id": target.active_schema_snapshot_id,
            "target_settings": target.target_settings,
            "property_rules": target.property_rules,
            "visibility": target.visibility,
        }
        try:
            await self._client.table(self.TABLE).upsert(row, on_conflict="id,owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_target_save_failed | id={} error={}", target.id, e)
            raise

    async def delete(self, id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            await self._client.table(self.TABLE).delete().eq("id", id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception("postgres_target_delete_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise


class PostgresTargetSchemaRepository:
    """Postgres-backed target schema snapshot repository."""

    TABLE = "target_schema_snapshots"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_by_id(self, id: str, owner_user_id: str) -> TargetSchemaSnapshot | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await self._client.table(self.TABLE).select("*").eq("id", id).eq("owner_user_id", uid).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_target_schema_get_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_target_schema_snapshot(rows[0], owner_user_id)

    async def list_by_owner(self, owner_user_id: str) -> list[TargetSchemaSnapshot]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).execute()
        except ValueError:
            return []
        except Exception as e:
            logger.exception("postgres_target_schema_list_failed | owner={} error={}", owner_user_id, e)
            raise
        return [_row_to_target_schema_snapshot(row, owner_user_id) for row in (r.data or [])]

    async def get_active_for_target(
        self, data_target_id: str, owner_user_id: str
    ) -> TargetSchemaSnapshot | None:
        snaps = await self.list_by_owner(owner_user_id)
        for snap in snaps:
            if snap.data_target_id == data_target_id and snap.is_active:
                return snap
        return None

    async def get_fetched_at_for_snapshots(
        self, snapshot_ids: list[str], owner_user_id: str
    ) -> dict[str, datetime]:
        """Batch fetch fetched_at for given snapshot ids. Returns {id: fetched_at}."""
        if not snapshot_ids:
            return {}
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await (
                self._client.table(self.TABLE)
                .select("id, fetched_at")
                .eq("owner_user_id", uid)
                .in_("id", snapshot_ids)
                .execute()
            )
        except ValueError:
            return {}
        except Exception as e:
            logger.exception(
                "postgres_target_schema_get_fetched_at_failed | owner={} error={}",
                owner_user_id,
                e,
            )
            raise
        result: dict[str, datetime] = {}
        for row in r.data or []:
            fetched = row.get("fetched_at")
            if fetched is not None:
                parsed = _parse_opt_datetime(fetched)
                if parsed:
                    result[row["id"]] = parsed
        return result

    async def save(self, snapshot: TargetSchemaSnapshot) -> None:
        uid = str(_ensure_uuid(snapshot.owner_user_id))
        props = [
            {
                "id": p.id,
                "external_property_id": p.external_property_id,
                "name": p.name,
                "normalized_slug": p.normalized_slug,
                "property_type": p.property_type,
                "required": p.required,
                "readonly": p.readonly,
                "options": p.options,
                "metadata": p.metadata,
            }
            for p in snapshot.properties
        ]
        fetched = snapshot.fetched_at
        if hasattr(fetched, "isoformat"):
            fetched = fetched.isoformat()
        row = {
            "id": snapshot.id,
            "owner_user_id": uid,
            "data_target_id": snapshot.data_target_id,
            "version": snapshot.version,
            "fetched_at": fetched,
            "is_active": snapshot.is_active,
            "source_connector_instance_id": snapshot.source_connector_instance_id,
            "properties": props,
            "raw_source_payload": snapshot.raw_source_payload,
        }
        try:
            await self._client.table(self.TABLE).upsert(row, on_conflict="id,owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_target_schema_save_failed | id={} error={}", snapshot.id, e)
            raise

    async def delete(self, id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            await self._client.table(self.TABLE).delete().eq("id", id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception("postgres_target_schema_delete_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise


class PostgresTriggerRepository:
    """Postgres-backed trigger definition repository."""

    TABLE = "trigger_definitions"

    def __init__(
        self,
        client: AsyncClient,
        validation_service: ValidationService | None = None,
    ) -> None:
        self._client = client
        self._validation_service = validation_service

    def set_validation_service(self, validation_service: ValidationService | None) -> None:
        self._validation_service = validation_service

    async def get_by_id(self, id: str, owner_user_id: str) -> TriggerDefinition | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await self._client.table(self.TABLE).select("*").eq("id", id).eq("owner_user_id", uid).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_trigger_get_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_trigger(rows[0], owner_user_id)

    async def get_by_path(self, path: str, owner_user_id: str) -> TriggerDefinition | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).eq("path", path).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_trigger_get_by_path_failed | path={} owner={} error={}", path, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_trigger(rows[0], owner_user_id)

    async def list_by_owner(self, owner_user_id: str) -> list[TriggerDefinition]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).execute()
        except ValueError:
            return []
        except Exception as e:
            logger.exception("postgres_trigger_list_failed | owner={} error={}", owner_user_id, e)
            raise
        return [_row_to_trigger(row, owner_user_id) for row in (r.data or [])]

    async def save(self, trigger: TriggerDefinition) -> None:
        if self._validation_service:
            await self._validation_service.validate_trigger(trigger)
        uid = str(_ensure_uuid(trigger.owner_user_id))
        secret_rotated = trigger.secret_last_rotated_at
        if hasattr(secret_rotated, "isoformat"):
            secret_rotated = secret_rotated.isoformat()
        row = {
            "id": trigger.id,
            "owner_user_id": uid,
            "trigger_type": trigger.trigger_type,
            "display_name": trigger.display_name,
            "path": trigger.path,
            "method": trigger.method,
            "request_body_schema": trigger.request_body_schema,
            "status": trigger.status,
            "auth_mode": trigger.auth_mode,
            "secret_value": trigger.secret_value,
            "secret_last_rotated_at": secret_rotated,
            "visibility": trigger.visibility,
        }
        try:
            await self._client.table(self.TABLE).upsert(row, on_conflict="id,owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_trigger_save_failed | id={} error={}", trigger.id, e)
            raise

    async def delete(self, id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            await self._client.table(self.TABLE).delete().eq("id", id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception("postgres_trigger_delete_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise

    async def rotate_secret(self, id: str, owner_user_id: str) -> tuple[TriggerDefinition, str]:
        """
        Generate a new secret for the trigger, persist it, and return (updated trigger, new_plaintext_secret).
        """
        trigger = await self.get_by_id(id, owner_user_id)
        if not trigger:
            raise ValueError(f"Trigger not found: id={id} owner={owner_user_id}")
        new_secret = secrets.token_hex(15)  # ~30 chars
        now = datetime.now(timezone.utc)
        updated = TriggerDefinition(
            id=trigger.id,
            owner_user_id=trigger.owner_user_id,
            trigger_type=trigger.trigger_type,
            display_name=trigger.display_name,
            path=trigger.path,
            method=trigger.method,
            request_body_schema=trigger.request_body_schema,
            status=trigger.status,
            auth_mode=trigger.auth_mode,
            secret_value=new_secret,
            secret_last_rotated_at=now,
            visibility=trigger.visibility,
            created_at=trigger.created_at,
            updated_at=now,
        )
        await self.save(updated)
        return updated, new_secret


class PostgresTriggerJobLinkRepository:
    """Postgres-backed many-to-many trigger-job associations."""

    TABLE = "trigger_job_links"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def list_job_ids_for_trigger(
        self, trigger_id: str, owner_user_id: str
    ) -> list[str]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await (
                self._client.table(self.TABLE)
                .select("job_id")
                .eq("trigger_id", trigger_id)
                .eq("owner_user_id", uid)
                .execute()
            )
        except ValueError:
            return []
        except Exception as e:
            logger.exception(
                "postgres_trigger_job_links_list_jobs_failed | trigger_id={} owner={} error={}",
                trigger_id,
                owner_user_id,
                e,
            )
            raise
        return [row["job_id"] for row in (r.data or [])]

    async def list_dispatchable_job_ids_for_trigger(
        self, trigger_id: str, owner_user_id: str
    ) -> list[str]:
        """Linked job IDs with status ``active``, same order as link rows."""
        linked = await self.list_job_ids_for_trigger(trigger_id, owner_user_id)
        if not linked:
            return []
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await (
                self._client.table("job_definitions")
                .select("id")
                .eq("owner_user_id", uid)
                .in_("id", linked)
                .eq("status", "active")
                .execute()
            )
        except ValueError:
            return []
        except Exception as e:
            logger.exception(
                "postgres_job_list_dispatchable_for_trigger_failed | trigger_id={} owner={} error={}",
                trigger_id,
                owner_user_id,
                e,
            )
            raise
        active_ids = {row["id"] for row in (r.data or [])}
        return [jid for jid in linked if jid in active_ids]

    async def list_trigger_ids_for_job(
        self, job_id: str, owner_user_id: str
    ) -> list[str]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await (
                self._client.table(self.TABLE)
                .select("trigger_id")
                .eq("job_id", job_id)
                .eq("owner_user_id", uid)
                .execute()
            )
        except ValueError:
            return []
        except Exception as e:
            logger.exception(
                "postgres_trigger_job_links_list_triggers_failed | job_id={} owner={} error={}",
                job_id,
                owner_user_id,
                e,
            )
            raise
        ids = [row["trigger_id"] for row in (r.data or [])]
        return sorted(ids)

    async def map_trigger_ids_for_jobs(
        self, owner_user_id: str, job_ids: list[str]
    ) -> dict[str, list[str]]:
        """
        Return sorted trigger_id lists per job_id in one query (owner-scoped).
        Jobs with no rows map to an empty list.
        """
        if not job_ids:
            return {}
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await (
                self._client.table(self.TABLE)
                .select("job_id, trigger_id")
                .eq("owner_user_id", uid)
                .in_("job_id", job_ids)
                .execute()
            )
        except ValueError:
            return {jid: [] for jid in job_ids}
        except Exception as e:
            logger.exception(
                "postgres_trigger_job_links_map_jobs_failed | owner={} n_jobs={} error={}",
                owner_user_id,
                len(job_ids),
                e,
            )
            raise
        by_job: dict[str, list[str]] = {jid: [] for jid in job_ids}
        for row in r.data or []:
            jid = row.get("job_id")
            tid = row.get("trigger_id")
            if jid and tid and jid in by_job:
                by_job[jid].append(tid)
        for jid in by_job:
            by_job[jid] = sorted(by_job[jid])
        return by_job

    async def attach(self, trigger_id: str, job_id: str, owner_user_id: str) -> None:
        existing = await self.list_trigger_ids_for_job(job_id, owner_user_id)
        validate_one_trigger_per_job_attach(existing, trigger_id)

        uid = str(_ensure_uuid(owner_user_id))
        row = {
            "trigger_id": trigger_id,
            "job_id": job_id,
            "owner_user_id": uid,
        }
        try:
            await self._client.table(self.TABLE).upsert(
                row, on_conflict="trigger_id,job_id,owner_user_id"
            ).execute()
        except Exception as e:
            logger.exception(
                "postgres_trigger_job_links_attach_failed | trigger_id={} job_id={} error={}",
                trigger_id,
                job_id,
                e,
            )
            raise

    async def detach(self, trigger_id: str, job_id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            await self._client.table(self.TABLE).delete().eq(
                "trigger_id", trigger_id
            ).eq("job_id", job_id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception(
                "postgres_trigger_job_links_detach_failed | trigger_id={} job_id={} owner={} error={}",
                trigger_id,
                job_id,
                owner_user_id,
                e,
            )
            raise


class PostgresJobRepository:
    """Postgres-backed job definition repository with full graph support."""

    JOB_TABLE = "job_definitions"
    STAGE_TABLE = "stage_definitions"
    PIPELINE_TABLE = "pipeline_definitions"
    STEP_TABLE = "step_instances"

    def __init__(
        self,
        client: AsyncClient,
        validation_service: ValidationService | None = None,
    ) -> None:
        self._client = client
        self._validation_service = validation_service

    def set_validation_service(self, validation_service: ValidationService | None) -> None:
        self._validation_service = validation_service

    async def get_bootstrap_job(self, job_slug: str) -> JobDefinition | None:
        # In Postgres mode, bootstrap is provisioned per-owner; no global bootstrap row.
        return None

    async def get_by_id(self, id: str, owner_user_id: str) -> JobDefinition | None:
        graph = await self.get_graph_by_id(id, owner_user_id)
        return graph.job if graph else None

    async def get_graph_by_id(self, id: str, owner_user_id: str) -> JobGraph | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
        except ValueError:
            return None
        try:
            r = await self._client.table(self.JOB_TABLE).select("*").eq("id", id).eq("owner_user_id", uid).limit(1).execute()
        except Exception as e:
            logger.exception("postgres_job_get_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        job_row = rows[0]
        if str(job_row.get("status", "active")) == "archived":
            return None
        job = _row_to_job(job_row, owner_user_id)

        # Load stages
        r_stages = await (
            self._client.table(self.STAGE_TABLE)
            .select("*")
            .eq("job_id", id)
            .eq("owner_user_id", uid)
            .order("sequence")
            .execute()
        )
        stage_rows = r_stages.data or []
        stages: list[StageDefinition] = []
        pipelines: list[PipelineDefinition] = []
        steps: list[StepInstance] = []

        for srow in stage_rows:
            stage = _row_to_stage(srow, id, owner_user_id)
            stages.append(stage)

            # Load pipelines for this stage
            r_pipes = await (
                self._client.table(self.PIPELINE_TABLE)
                .select("*")
                .eq("stage_id", stage.id)
                .eq("owner_user_id", uid)
                .order("sequence")
                .execute()
            )
            pipe_rows = r_pipes.data or []
            for prow in pipe_rows:
                pipe = _row_to_pipeline(prow, stage.id, owner_user_id)
                pipelines.append(pipe)

                # Load steps for this pipeline
                r_steps = await (
                    self._client.table(self.STEP_TABLE)
                    .select("*")
                    .eq("pipeline_id", pipe.id)
                    .eq("owner_user_id", uid)
                    .order("sequence")
                    .execute()
                )
                step_rows = r_steps.data or []
                for strow in step_rows:
                    steps.append(_row_to_step_instance(strow, pipe.id, owner_user_id))

        return JobGraph(job=job, stages=stages, pipelines=pipelines, steps=steps)

    async def list_by_owner(self, owner_user_id: str) -> list[JobDefinition]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await (
                self._client.table(self.JOB_TABLE)
                .select("*")
                .eq("owner_user_id", uid)
                .neq("status", "archived")
                .execute()
            )
        except ValueError:
            return []
        except Exception as e:
            logger.exception("postgres_job_list_failed | owner={} error={}", owner_user_id, e)
            raise
        return [_row_to_job(row, owner_user_id) for row in (r.data or [])]

    async def save(self, job: JobDefinition) -> None:
        uid = str(_ensure_uuid(job.owner_user_id))
        row = {
            "id": job.id,
            "owner_user_id": uid,
            "display_name": job.display_name,
            "target_id": job.target_id,
            "status": job.status,
            "stage_ids": job.stage_ids,
            "default_run_settings": job.default_run_settings,
            "visibility": job.visibility,
        }
        if job.updated_at is not None:
            row["updated_at"] = job.updated_at.isoformat()
        try:
            await self._client.table(self.JOB_TABLE).upsert(row, on_conflict="id,owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_job_save_failed | id={} error={}", job.id, e)
            raise

    async def update_job_status(self, id: str, owner_user_id: str, status: str) -> None:
        """Update job row status and updated_at only (no graph validation or child rows)."""
        try:
            uid = str(_ensure_uuid(owner_user_id))
            now = datetime.now(timezone.utc).isoformat()
            await self._client.table(self.JOB_TABLE).update({"status": status, "updated_at": now}).eq(
                "id", id
            ).eq("owner_user_id", uid).execute()
        except ValueError:
            return
        except Exception as e:
            logger.exception("postgres_job_update_status_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise

    async def save_job_graph(
        self,
        graph: JobGraph,
        *,
        skip_reference_checks: bool = False,
    ) -> None:
        if self._validation_service:
            await self._validation_service.validate_job_graph(
                graph, skip_reference_checks=skip_reference_checks
            )
        job = graph.job
        uid = str(_ensure_uuid(job.owner_user_id))

        # Upsert job
        await self.save(job)

        # Upsert stages
        for stage in graph.stages:
            row = {
                "id": stage.id,
                "job_id": job.id,
                "owner_user_id": uid,
                "display_name": stage.display_name,
                "sequence": _seq_int(stage.sequence),
                "pipeline_ids": stage.pipeline_ids,
                "pipeline_run_mode": stage.pipeline_run_mode,
            }
            await self._client.table(self.STAGE_TABLE).upsert(row, on_conflict="id,owner_user_id").execute()

        # Upsert pipelines and steps
        for pipeline in graph.pipelines:
            prow = {
                "id": pipeline.id,
                "stage_id": pipeline.stage_id,
                "owner_user_id": uid,
                "display_name": pipeline.display_name,
                "sequence": _seq_int(pipeline.sequence),
                "step_ids": pipeline.step_ids,
                "purpose": pipeline.purpose,
            }
            await self._client.table(self.PIPELINE_TABLE).upsert(prow, on_conflict="id,owner_user_id").execute()

            steps_for_pipeline = [s for s in graph.steps if s.pipeline_id == pipeline.id]
            steps_ordered = sorted(
                steps_for_pipeline,
                key=lambda s: (_seq_int(s.sequence), s.id),
            )
            wanted_step_ids = [s.id for s in steps_ordered]

            # Saved graph is authoritative for which step ids exist. Remove orphan rows *before*
            # writing final sequences: leftover rows still hold 1..n slots and would violate
            # uq_step_sequence_per_pipeline during the second upsert phase.
            if not wanted_step_ids:
                await (
                    self._client.table(self.STEP_TABLE)
                    .delete()
                    .eq("pipeline_id", pipeline.id)
                    .eq("owner_user_id", uid)
                    .execute()
                )
                continue

            await (
                self._client.table(self.STEP_TABLE)
                .delete()
                .eq("pipeline_id", pipeline.id)
                .eq("owner_user_id", uid)
                .not_.in_("id", wanted_step_ids)
                .execute()
            )

            # Two-phase upsert: per-row upserts can collide on (pipeline_id, owner_user_id, sequence)
            # when reordering (e.g. swap 1<->2). Move all steps to a temp band, then write 1..n.
            for i, step in enumerate(steps_ordered):
                srow = _step_instance_row(step, pipeline.id, uid, _STEP_SEQUENCE_TEMP_BASE + i)
                await self._client.table(self.STEP_TABLE).upsert(srow, on_conflict="id,owner_user_id").execute()
            for i, step in enumerate(steps_ordered):
                srow = _step_instance_row(step, pipeline.id, uid, i + 1)
                await self._client.table(self.STEP_TABLE).upsert(srow, on_conflict="id,owner_user_id").execute()

    async def archive(self, id: str, owner_user_id: str) -> None:
        """Soft-delete: set status to archived. Archived jobs are excluded from list and get_graph_by_id."""
        try:
            uid = str(_ensure_uuid(owner_user_id))
            now = datetime.now(timezone.utc).isoformat()
            await self._client.table(self.JOB_TABLE).update(
                {"status": "archived", "updated_at": now}
            ).eq("id", id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception("postgres_job_archive_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise

    async def delete(self, id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            # Cascade will remove stages, pipelines, steps
            await self._client.table(self.JOB_TABLE).delete().eq("id", id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception("postgres_job_delete_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise


class PostgresAppConfigRepository:
    """Postgres-backed app config (limits) repository."""

    TABLE = "app_limits"
    NEW_USER_DEFAULTS_TABLE = "app_limits_new_user_defaults"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_global_row(self) -> dict[str, Any] | None:
        """Return the platform global limits row (``owner_user_id`` IS NULL), or None."""
        try:
            r = await self._client.table(self.TABLE).select("*").is_("owner_user_id", "null").limit(1).execute()
        except Exception as e:
            logger.exception("postgres_app_config_get_global_failed | error={}", e)
            raise
        rows = r.data or []
        return rows[0] if rows else None

    async def get_user_row(self, owner_user_id: str) -> dict[str, Any] | None:
        """Return the per-owner ``app_limits`` row if present."""
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = await self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_app_config_get_user_row_failed | owner={} error={}", owner_user_id, e)
            raise
        rows = r.data or []
        return rows[0] if rows else None

    async def get_by_owner(self, owner_user_id: str) -> AppLimits | None:
        from app.services.effective_limits import LimitsResolutionError, resolve_effective_app_limits

        g = await self.get_global_row()
        if not g:
            return None
        u = await self.get_user_row(owner_user_id)
        try:
            return resolve_effective_app_limits(
                g,
                u,
                owner_user_id=owner_user_id,
                operation="get_by_owner",
            )
        except LimitsResolutionError as e:
            logger.warning(
                "postgres_app_limits_resolve_failed | owner={} error={}",
                owner_user_id,
                e,
            )
            return None

    async def save(self, owner_user_id: str, limits: AppLimits) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            row = {
                "owner_user_id": uid,
                "max_stages_per_job": limits.max_stages_per_job,
                "max_pipelines_per_stage": limits.max_pipelines_per_stage,
                "max_steps_per_pipeline": limits.max_steps_per_pipeline,
                "max_jobs_per_owner": limits.max_jobs_per_owner,
                "max_triggers_per_owner": limits.max_triggers_per_owner,
                "max_runs_per_utc_day": limits.max_runs_per_utc_day,
                "max_runs_per_utc_month": limits.max_runs_per_utc_month,
            }
            await self._client.table(self.TABLE).upsert(row, on_conflict="owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_app_config_save_failed | owner={} error={}", owner_user_id, e)
            raise

    async def upsert_global_row(self, limits: AppLimits) -> None:
        """Replace platform global row (service role / admin only)."""
        try:
            payload = {
                "max_stages_per_job": limits.max_stages_per_job,
                "max_pipelines_per_stage": limits.max_pipelines_per_stage,
                "max_steps_per_pipeline": limits.max_steps_per_pipeline,
                "max_jobs_per_owner": limits.max_jobs_per_owner,
                "max_triggers_per_owner": limits.max_triggers_per_owner,
                "max_runs_per_utc_day": limits.max_runs_per_utc_day,
                "max_runs_per_utc_month": limits.max_runs_per_utc_month,
            }
            ex = await self.get_global_row()
            if ex:
                await self._client.table(self.TABLE).update(payload).eq("id", ex["id"]).execute()
            else:
                row = {"owner_user_id": None, **payload}
                await self._client.table(self.TABLE).insert(row).execute()
        except Exception as e:
            logger.exception("postgres_app_config_upsert_global_failed | error={}", e)
            raise

    async def get_new_user_defaults_row(self) -> dict[str, Any] | None:
        """Single-row template copied to new owners at provisioning (not used in runtime merge)."""
        try:
            r = await self._client.table(self.NEW_USER_DEFAULTS_TABLE).select("*").eq("id", 1).limit(1).execute()
        except Exception as e:
            logger.exception("postgres_app_limits_new_user_defaults_get_failed | error={}", e)
            raise
        rows = r.data or []
        return rows[0] if rows else None

    async def upsert_new_user_defaults(self, limits: AppLimits) -> None:
        """Admin: replace id=1 row in ``app_limits_new_user_defaults``."""
        try:
            row = {
                "id": 1,
                "max_stages_per_job": limits.max_stages_per_job,
                "max_pipelines_per_stage": limits.max_pipelines_per_stage,
                "max_steps_per_pipeline": limits.max_steps_per_pipeline,
                "max_jobs_per_owner": limits.max_jobs_per_owner,
                "max_triggers_per_owner": limits.max_triggers_per_owner,
                "max_runs_per_utc_day": limits.max_runs_per_utc_day,
                "max_runs_per_utc_month": limits.max_runs_per_utc_month,
            }
            await self._client.table(self.NEW_USER_DEFAULTS_TABLE).upsert(row, on_conflict="id").execute()
        except Exception as e:
            logger.exception("postgres_app_limits_new_user_defaults_upsert_failed | error={}", e)
            raise

    async def seed_user_limits_from_defaults_if_missing(self, owner_user_id: str) -> None:
        """Insert per-owner ``app_limits`` from ``app_limits_new_user_defaults`` when no user row exists."""
        if await self.get_user_row(owner_user_id) is not None:
            return
        d = await self.get_new_user_defaults_row()
        if not d:
            return
        try:
            limits = AppLimits(
                max_stages_per_job=int(d["max_stages_per_job"]),
                max_pipelines_per_stage=int(d["max_pipelines_per_stage"]),
                max_steps_per_pipeline=int(d["max_steps_per_pipeline"]),
                max_jobs_per_owner=int(d["max_jobs_per_owner"]),
                max_triggers_per_owner=int(d["max_triggers_per_owner"]),
                max_runs_per_utc_day=int(d["max_runs_per_utc_day"]),
                max_runs_per_utc_month=int(d["max_runs_per_utc_month"]),
            )
            await self.save(owner_user_id, limits)
            logger.info("app_limits_seeded_from_new_user_defaults | owner={}", owner_user_id)
        except Exception as e:
            logger.warning(
                "app_limits_seed_from_defaults_failed | owner={} error={}",
                owner_user_id,
                e,
            )


class PostgresOAuthConnectionStateRepository:
    """Postgres-backed OAuth state for CSRF/anti-replay."""

    TABLE = "oauth_connection_states"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def create(
        self,
        owner_user_id: str,
        provider: str,
        state_token_hash: str,
        redirect_uri: str,
        expires_at: datetime,
        pkce_verifier_encrypted: str | None = None,
    ) -> str:
        uid = str(_ensure_uuid(owner_user_id))
        row = {
            "owner_user_id": uid,
            "provider": provider,
            "state_token_hash": state_token_hash,
            "pkce_verifier_encrypted": pkce_verifier_encrypted,
            "redirect_uri": redirect_uri,
            "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else expires_at,
        }
        r = await self._client.table(self.TABLE).insert(row).execute()
        rows = r.data or []
        if not rows:
            raise RuntimeError("oauth_state_insert_failed")
        return str(rows[0]["id"])

    async def consume_by_state_hash(self, state_token_hash: str) -> dict[str, Any] | None:
        """Find and consume state by hash. Returns row with owner_user_id; None if invalid/expired."""
        now = datetime.now(timezone.utc).isoformat()
        r = await (
            self._client.table(self.TABLE)
            .select("*")
            .eq("state_token_hash", state_token_hash)
            .is_("consumed_at", "null")
            .execute()
        )
        rows = r.data or []
        if not rows:
            return None
        row = rows[0]
        exp = row.get("expires_at")
        if exp:
            exp_str = exp.isoformat() if hasattr(exp, "isoformat") else str(exp)
            if exp_str < now:
                return None
        await self._client.table(self.TABLE).update({"consumed_at": now}).eq("id", row["id"]).execute()
        return row


class PostgresConnectorCredentialsRepository:
    """Postgres-backed connector OAuth credentials."""

    TABLE = "connector_credentials"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_for_instance(
        self, connector_instance_id: str, owner_user_id: str, provider: str = "notion"
    ) -> dict[str, Any] | None:
        uid = str(_ensure_uuid(owner_user_id))
        r = await (
            self._client.table(self.TABLE)
            .select("*")
            .eq("connector_instance_id", connector_instance_id)
            .eq("owner_user_id", uid)
            .eq("provider", provider)
            .is_("revoked_at", "null")
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return rows[0] if rows else None

    async def upsert(
        self,
        connector_instance_id: str,
        owner_user_id: str,
        provider: str,
        secret_ref: str,
        token_payload: dict[str, Any],
        token_expires_at: datetime | None = None,
    ) -> None:
        uid = str(_ensure_uuid(owner_user_id))
        now = datetime.now(timezone.utc)
        row = {
            "owner_user_id": uid,
            "connector_instance_id": connector_instance_id,
            "provider": provider,
            "credential_type": "oauth2",
            "secret_ref": secret_ref,
            "token_payload": token_payload,
            "token_expires_at": token_expires_at.isoformat() if token_expires_at else None,
            "last_refreshed_at": now.isoformat(),
            "updated_at": now.isoformat(),
            # Re-connecting should reactivate credentials that were previously revoked.
            "revoked_at": None,
        }
        await self._client.table(self.TABLE).upsert(
            row, on_conflict="owner_user_id,connector_instance_id,provider,credential_type"
        ).execute()

    async def revoke(self, connector_instance_id: str, owner_user_id: str, provider: str = "notion") -> None:
        uid = str(_ensure_uuid(owner_user_id))
        now = datetime.now(timezone.utc).isoformat()
        await self._client.table(self.TABLE).update({"revoked_at": now}).eq(
            "connector_instance_id", connector_instance_id
        ).eq("owner_user_id", uid).eq("provider", provider).execute()


class PostgresConnectorExternalSourcesRepository:
    """Postgres-backed discovered external sources (e.g. Notion databases)."""

    TABLE = "connector_external_sources"

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def list_for_instance(
        self, connector_instance_id: str, owner_user_id: str, provider: str = "notion"
    ) -> list[dict[str, Any]]:
        uid = str(_ensure_uuid(owner_user_id))
        r = await (
            self._client.table(self.TABLE)
            .select("*")
            .eq("connector_instance_id", connector_instance_id)
            .eq("owner_user_id", uid)
            .eq("provider", provider)
            .execute()
        )
        return r.data or []

    async def upsert_batch(
        self,
        connector_instance_id: str,
        owner_user_id: str,
        provider: str,
        sources: list[dict[str, Any]],
    ) -> None:
        uid = str(_ensure_uuid(owner_user_id))
        now = datetime.now(timezone.utc).isoformat()
        for s in sources:
            row = {
                "owner_user_id": uid,
                "connector_instance_id": connector_instance_id,
                "provider": provider,
                "external_source_id": s["external_source_id"],
                "external_parent_id": s.get("external_parent_id"),
                "display_name": s.get("display_name", s["external_source_id"]),
                "is_accessible": s.get("is_accessible", True),
                "last_seen_at": now,
                "last_sync_error": s.get("last_sync_error"),
                "updated_at": now,
            }
            await self._client.table(self.TABLE).upsert(
                row, on_conflict="owner_user_id,connector_instance_id,external_source_id"
            ).execute()
