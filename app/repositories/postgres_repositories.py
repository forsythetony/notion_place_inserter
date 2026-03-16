"""Postgres-backed repository implementations for Phase 4 datastore."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from loguru import logger
from supabase import Client

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
    )


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

    def __init__(self, client: Client) -> None:
        self._client = client

    def get_by_id(self, id: str) -> ConnectorTemplate | None:
        try:
            r = self._client.table(self.TABLE).select("*").eq("id", id).limit(1).execute()
        except Exception as e:
            logger.exception("postgres_connector_template_get_failed | id={} error={}", id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_connector_template(rows[0])

    def list_all(self) -> list[ConnectorTemplate]:
        try:
            r = self._client.table(self.TABLE).select("*").execute()
        except Exception as e:
            logger.exception("postgres_connector_template_list_failed | error={}", e)
            raise
        return [_row_to_connector_template(row) for row in (r.data or [])]

    def save(self, template: ConnectorTemplate) -> None:
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
            self._client.table(self.TABLE).upsert(row, on_conflict="id").execute()
        except Exception as e:
            logger.exception("postgres_connector_template_save_failed | id={} error={}", template.id, e)
            raise

    def delete(self, id: str) -> None:
        try:
            self._client.table(self.TABLE).delete().eq("id", id).execute()
        except Exception as e:
            logger.exception("postgres_connector_template_delete_failed | id={} error={}", id, e)
            raise


class PostgresTargetTemplateRepository:
    """Postgres-backed target template catalog."""

    TABLE = "target_templates"

    def __init__(self, client: Client) -> None:
        self._client = client

    def get_by_id(self, id: str) -> TargetTemplate | None:
        try:
            r = self._client.table(self.TABLE).select("*").eq("id", id).limit(1).execute()
        except Exception as e:
            logger.exception("postgres_target_template_get_failed | id={} error={}", id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_target_template(rows[0])

    def list_all(self) -> list[TargetTemplate]:
        try:
            r = self._client.table(self.TABLE).select("*").execute()
        except Exception as e:
            logger.exception("postgres_target_template_list_failed | error={}", e)
            raise
        return [_row_to_target_template(row) for row in (r.data or [])]

    def save(self, template: TargetTemplate) -> None:
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
            self._client.table(self.TABLE).upsert(row, on_conflict="id").execute()
        except Exception as e:
            logger.exception("postgres_target_template_save_failed | id={} error={}", template.id, e)
            raise

    def delete(self, id: str) -> None:
        try:
            self._client.table(self.TABLE).delete().eq("id", id).execute()
        except Exception as e:
            logger.exception("postgres_target_template_delete_failed | id={} error={}", id, e)
            raise


class PostgresStepTemplateRepository:
    """Postgres-backed step template catalog."""

    TABLE = "step_templates"

    def __init__(self, client: Client) -> None:
        self._client = client

    def get_by_id(self, id: str) -> StepTemplate | None:
        try:
            r = self._client.table(self.TABLE).select("*").eq("id", id).limit(1).execute()
        except Exception as e:
            logger.exception("postgres_step_template_get_failed | id={} error={}", id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_step_template(rows[0])

    def list_all(self) -> list[StepTemplate]:
        try:
            r = self._client.table(self.TABLE).select("*").execute()
        except Exception as e:
            logger.exception("postgres_step_template_list_failed | error={}", e)
            raise
        return [_row_to_step_template(row) for row in (r.data or [])]

    def save(self, template: StepTemplate) -> None:
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
        }
        try:
            self._client.table(self.TABLE).upsert(row, on_conflict="id").execute()
        except Exception as e:
            logger.exception("postgres_step_template_save_failed | id={} error={}", template.id, e)
            raise

    def delete(self, id: str) -> None:
        try:
            self._client.table(self.TABLE).delete().eq("id", id).execute()
        except Exception as e:
            logger.exception("postgres_step_template_delete_failed | id={} error={}", id, e)
            raise


class PostgresConnectorInstanceRepository:
    """Postgres-backed connector instance repository."""

    TABLE = "connector_instances"

    def __init__(self, client: Client) -> None:
        self._client = client

    def get_by_id(self, id: str, owner_user_id: str) -> ConnectorInstance | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = self._client.table(self.TABLE).select("*").eq("id", id).eq("owner_user_id", uid).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_connector_instance_get_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_connector_instance(rows[0], owner_user_id)

    def list_by_owner(self, owner_user_id: str) -> list[ConnectorInstance]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).execute()
        except ValueError:
            return []
        except Exception as e:
            logger.exception("postgres_connector_instance_list_failed | owner={} error={}", owner_user_id, e)
            raise
        return [_row_to_connector_instance(row, owner_user_id) for row in (r.data or [])]

    def save(self, instance: ConnectorInstance) -> None:
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
        }
        try:
            self._client.table(self.TABLE).upsert(row, on_conflict="id,owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_connector_instance_save_failed | id={} error={}", instance.id, e)
            raise

    def delete(self, id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            self._client.table(self.TABLE).delete().eq("id", id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception("postgres_connector_instance_delete_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise


class PostgresTargetRepository:
    """Postgres-backed data target repository."""

    TABLE = "data_targets"

    def __init__(
        self,
        client: Client,
        validation_service: ValidationService | None = None,
    ) -> None:
        self._client = client
        self._validation_service = validation_service

    def set_validation_service(self, validation_service: ValidationService | None) -> None:
        self._validation_service = validation_service

    def get_by_id(self, id: str, owner_user_id: str) -> DataTarget | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = self._client.table(self.TABLE).select("*").eq("id", id).eq("owner_user_id", uid).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_target_get_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_data_target(rows[0], owner_user_id)

    def list_by_owner(self, owner_user_id: str) -> list[DataTarget]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).execute()
        except ValueError:
            return []
        except Exception as e:
            logger.exception("postgres_target_list_failed | owner={} error={}", owner_user_id, e)
            raise
        return [_row_to_data_target(row, owner_user_id) for row in (r.data or [])]

    def save(self, target: DataTarget) -> None:
        if self._validation_service:
            self._validation_service.validate_data_target(target)
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
            self._client.table(self.TABLE).upsert(row, on_conflict="id,owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_target_save_failed | id={} error={}", target.id, e)
            raise

    def delete(self, id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            self._client.table(self.TABLE).delete().eq("id", id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception("postgres_target_delete_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise


class PostgresTargetSchemaRepository:
    """Postgres-backed target schema snapshot repository."""

    TABLE = "target_schema_snapshots"

    def __init__(self, client: Client) -> None:
        self._client = client

    def get_by_id(self, id: str, owner_user_id: str) -> TargetSchemaSnapshot | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = self._client.table(self.TABLE).select("*").eq("id", id).eq("owner_user_id", uid).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_target_schema_get_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_target_schema_snapshot(rows[0], owner_user_id)

    def list_by_owner(self, owner_user_id: str) -> list[TargetSchemaSnapshot]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).execute()
        except ValueError:
            return []
        except Exception as e:
            logger.exception("postgres_target_schema_list_failed | owner={} error={}", owner_user_id, e)
            raise
        return [_row_to_target_schema_snapshot(row, owner_user_id) for row in (r.data or [])]

    def get_active_for_target(
        self, data_target_id: str, owner_user_id: str
    ) -> TargetSchemaSnapshot | None:
        for snap in self.list_by_owner(owner_user_id):
            if snap.data_target_id == data_target_id and snap.is_active:
                return snap
        return None

    def save(self, snapshot: TargetSchemaSnapshot) -> None:
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
            self._client.table(self.TABLE).upsert(row, on_conflict="id,owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_target_schema_save_failed | id={} error={}", snapshot.id, e)
            raise

    def delete(self, id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            self._client.table(self.TABLE).delete().eq("id", id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception("postgres_target_schema_delete_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise


class PostgresTriggerRepository:
    """Postgres-backed trigger definition repository."""

    TABLE = "trigger_definitions"

    def __init__(
        self,
        client: Client,
        validation_service: ValidationService | None = None,
    ) -> None:
        self._client = client
        self._validation_service = validation_service

    def set_validation_service(self, validation_service: ValidationService | None) -> None:
        self._validation_service = validation_service

    def get_by_id(self, id: str, owner_user_id: str) -> TriggerDefinition | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = self._client.table(self.TABLE).select("*").eq("id", id).eq("owner_user_id", uid).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_trigger_get_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_trigger(rows[0], owner_user_id)

    def get_by_path(self, path: str, owner_user_id: str) -> TriggerDefinition | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).eq("path", path).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_trigger_get_by_path_failed | path={} owner={} error={}", path, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        return _row_to_trigger(rows[0], owner_user_id)

    def list_by_owner(self, owner_user_id: str) -> list[TriggerDefinition]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).execute()
        except ValueError:
            return []
        except Exception as e:
            logger.exception("postgres_trigger_list_failed | owner={} error={}", owner_user_id, e)
            raise
        return [_row_to_trigger(row, owner_user_id) for row in (r.data or [])]

    def save(self, trigger: TriggerDefinition) -> None:
        if self._validation_service:
            self._validation_service.validate_trigger(trigger)
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
            self._client.table(self.TABLE).upsert(row, on_conflict="id,owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_trigger_save_failed | id={} error={}", trigger.id, e)
            raise

    def delete(self, id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            self._client.table(self.TABLE).delete().eq("id", id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception("postgres_trigger_delete_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise

    def rotate_secret(self, id: str, owner_user_id: str) -> tuple[TriggerDefinition, str]:
        """
        Generate a new secret for the trigger, persist it, and return (updated trigger, new_plaintext_secret).
        """
        trigger = self.get_by_id(id, owner_user_id)
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
        self.save(updated)
        return updated, new_secret


class PostgresTriggerJobLinkRepository:
    """Postgres-backed many-to-many trigger-job associations."""

    TABLE = "trigger_job_links"

    def __init__(self, client: Client) -> None:
        self._client = client

    def list_job_ids_for_trigger(
        self, trigger_id: str, owner_user_id: str
    ) -> list[str]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = (
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

    def list_trigger_ids_for_job(
        self, job_id: str, owner_user_id: str
    ) -> list[str]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = (
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
        return [row["trigger_id"] for row in (r.data or [])]

    def attach(self, trigger_id: str, job_id: str, owner_user_id: str) -> None:
        uid = str(_ensure_uuid(owner_user_id))
        row = {
            "trigger_id": trigger_id,
            "job_id": job_id,
            "owner_user_id": uid,
        }
        try:
            self._client.table(self.TABLE).upsert(
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

    def detach(self, trigger_id: str, job_id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            self._client.table(self.TABLE).delete().eq(
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
        client: Client,
        validation_service: ValidationService | None = None,
    ) -> None:
        self._client = client
        self._validation_service = validation_service

    def set_validation_service(self, validation_service: ValidationService | None) -> None:
        self._validation_service = validation_service

    def get_bootstrap_job(self, job_slug: str) -> JobDefinition | None:
        # In Postgres mode, bootstrap is provisioned per-owner; no global bootstrap row.
        return None

    def get_by_id(self, id: str, owner_user_id: str) -> JobDefinition | None:
        graph = self.get_graph_by_id(id, owner_user_id)
        return graph.job if graph else None

    def get_graph_by_id(self, id: str, owner_user_id: str) -> JobGraph | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
        except ValueError:
            return None
        try:
            r = self._client.table(self.JOB_TABLE).select("*").eq("id", id).eq("owner_user_id", uid).limit(1).execute()
        except Exception as e:
            logger.exception("postgres_job_get_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise
        rows = r.data or []
        if not rows:
            return None
        job_row = rows[0]
        job = _row_to_job(job_row, owner_user_id)

        # Load stages
        r_stages = (
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
            r_pipes = (
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
                r_steps = (
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

    def list_by_owner(self, owner_user_id: str) -> list[JobDefinition]:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = self._client.table(self.JOB_TABLE).select("*").eq("owner_user_id", uid).execute()
        except ValueError:
            return []
        except Exception as e:
            logger.exception("postgres_job_list_failed | owner={} error={}", owner_user_id, e)
            raise
        return [_row_to_job(row, owner_user_id) for row in (r.data or [])]

    def save(self, job: JobDefinition) -> None:
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
        try:
            self._client.table(self.JOB_TABLE).upsert(row, on_conflict="id,owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_job_save_failed | id={} error={}", job.id, e)
            raise

    def save_job_graph(
        self,
        graph: JobGraph,
        *,
        skip_reference_checks: bool = False,
    ) -> None:
        if self._validation_service:
            self._validation_service.validate_job_graph(graph, skip_reference_checks=skip_reference_checks)
        job = graph.job
        uid = str(_ensure_uuid(job.owner_user_id))

        # Upsert job
        self.save(job)

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
            self._client.table(self.STAGE_TABLE).upsert(row, on_conflict="id,owner_user_id").execute()

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
            self._client.table(self.PIPELINE_TABLE).upsert(prow, on_conflict="id,owner_user_id").execute()

            for step in graph.steps:
                if step.pipeline_id != pipeline.id:
                    continue
                srow = {
                    "id": step.id,
                    "pipeline_id": pipeline.id,
                    "owner_user_id": uid,
                    "step_template_id": step.step_template_id,
                    "display_name": step.display_name,
                    "sequence": _seq_int(step.sequence),
                    "input_bindings": step.input_bindings,
                    "config": step.config,
                    "failure_policy": step.failure_policy,
                }
                self._client.table(self.STEP_TABLE).upsert(srow, on_conflict="id,owner_user_id").execute()

    def delete(self, id: str, owner_user_id: str) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            # Cascade will remove stages, pipelines, steps
            self._client.table(self.JOB_TABLE).delete().eq("id", id).eq("owner_user_id", uid).execute()
        except Exception as e:
            logger.exception("postgres_job_delete_failed | id={} owner={} error={}", id, owner_user_id, e)
            raise


class PostgresAppConfigRepository:
    """Postgres-backed app config (limits) repository."""

    TABLE = "app_limits"

    def __init__(self, client: Client) -> None:
        self._client = client

    def get_by_owner(self, owner_user_id: str) -> AppLimits | None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            r = self._client.table(self.TABLE).select("*").eq("owner_user_id", uid).limit(1).execute()
        except ValueError:
            return None
        except Exception as e:
            logger.exception("postgres_app_config_get_failed | owner={} error={}", owner_user_id, e)
            raise
        rows = r.data or []
        if rows:
            row = rows[0]
            return AppLimits(
                max_stages_per_job=row.get("max_stages_per_job", 20),
                max_pipelines_per_stage=row.get("max_pipelines_per_stage", 20),
                max_steps_per_pipeline=row.get("max_steps_per_pipeline", 50),
            )
        # Fall back to global default (owner_user_id IS NULL) if supported
        try:
            r = self._client.table(self.TABLE).select("*").is_("owner_user_id", "null").limit(1).execute()
            rows = r.data or []
            if rows:
                row = rows[0]
                return AppLimits(
                    max_stages_per_job=row.get("max_stages_per_job", 20),
                    max_pipelines_per_stage=row.get("max_pipelines_per_stage", 20),
                    max_steps_per_pipeline=row.get("max_steps_per_pipeline", 50),
                )
        except Exception:
            pass
        return None

    def save(self, owner_user_id: str, limits: AppLimits) -> None:
        try:
            uid = str(_ensure_uuid(owner_user_id))
            row = {
                "owner_user_id": uid,
                "max_stages_per_job": limits.max_stages_per_job,
                "max_pipelines_per_stage": limits.max_pipelines_per_stage,
                "max_steps_per_pipeline": limits.max_steps_per_pipeline,
            }
            self._client.table(self.TABLE).upsert(row, on_conflict="owner_user_id").execute()
        except Exception as e:
            logger.exception("postgres_app_config_save_failed | owner={} error={}", owner_user_id, e)
            raise
