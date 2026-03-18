"""YAML-backed repository implementations for Phase 3 catalog and bootstrap."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.domain import (
    AppLimits,
    ConnectorInstance,
    ConnectorTemplate,
    DataTarget,
    JobDefinition,
    StepTemplate,
    TargetSchemaSnapshot,
    TargetTemplate,
    TriggerDefinition,
)
from app.domain.yaml_layout import (
    PRODUCT_MODEL_ROOT,
    bootstrap_job_path,
    bootstrap_trigger_path,
    catalog_connector_template_path,
    catalog_step_template_path,
    catalog_target_template_path,
    tenant_app_config_path,
    tenant_connector_instance_path,
    tenant_connector_instances_dir,
    tenant_job_path,
    tenant_jobs_dir,
    tenant_target_path,
    tenant_target_schema_snapshot_path,
    tenant_target_schema_snapshots_dir,
    tenant_targets_dir,
    tenant_trigger_path,
    tenant_triggers_dir,
)
from app.services.validation_service import JobGraph, ValidationService

from app.repositories.yaml_loader import (
    domain_to_yaml_dict,
    dump_yaml_file,
    job_graph_to_yaml_dict,
    load_yaml_file,
    parse_app_limits,
    parse_connector_instance,
    parse_connector_template,
    parse_data_target,
    parse_job_definition,
    parse_job_graph,
    parse_step_template,
    parse_target_schema_snapshot,
    parse_target_template,
    parse_trigger_definition,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _list_yaml_files_in_dir(relative_dir: str) -> list[str]:
    """List .yaml filenames (without path) in a directory. Returns empty if dir missing."""
    root = _project_root()
    dir_path = root / relative_dir
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    return [f.stem for f in dir_path.glob("*.yaml")]


class YamlConnectorTemplateRepository:
    """Read-only catalog repository for connector templates."""

    def __init__(self, base: str = PRODUCT_MODEL_ROOT) -> None:
        self._base = base

    def get_by_id(self, id: str) -> ConnectorTemplate | None:
        path = catalog_connector_template_path(id, self._base)
        data = load_yaml_file(path)
        if data is None:
            return None
        try:
            return parse_connector_template(data)
        except (KeyError, TypeError):
            return None

    def list_all(self) -> list[ConnectorTemplate]:
        catalog_dir = f"{self._base}/catalog/connector_templates"
        ids = _list_yaml_files_in_dir(catalog_dir)
        result: list[ConnectorTemplate] = []
        for tid in ids:
            t = self.get_by_id(tid)
            if t is not None:
                result.append(t)
        return result

    def save(self, template: ConnectorTemplate) -> None:
        # Catalog is read-only
        pass

    def delete(self, id: str) -> None:
        # Catalog is read-only
        pass


class YamlTargetTemplateRepository:
    """Read-only catalog repository for target templates."""

    def __init__(self, base: str = PRODUCT_MODEL_ROOT) -> None:
        self._base = base

    def get_by_id(self, id: str) -> TargetTemplate | None:
        path = catalog_target_template_path(id, self._base)
        data = load_yaml_file(path)
        if data is None:
            return None
        try:
            return parse_target_template(data)
        except (KeyError, TypeError):
            return None

    def list_all(self) -> list[TargetTemplate]:
        catalog_dir = f"{self._base}/catalog/target_templates"
        ids = _list_yaml_files_in_dir(catalog_dir)
        result: list[TargetTemplate] = []
        for tid in ids:
            t = self.get_by_id(tid)
            if t is not None:
                result.append(t)
        return result

    def save(self, template: TargetTemplate) -> None:
        pass

    def delete(self, id: str) -> None:
        pass


class YamlStepTemplateRepository:
    """Read-only catalog repository for step templates."""

    def __init__(self, base: str = PRODUCT_MODEL_ROOT) -> None:
        self._base = base

    def get_by_id(self, id: str) -> StepTemplate | None:
        path = catalog_step_template_path(id, self._base)
        data = load_yaml_file(path)
        if data is None:
            return None
        try:
            return parse_step_template(data)
        except (KeyError, TypeError):
            return None

    def list_all(self) -> list[StepTemplate]:
        catalog_dir = f"{self._base}/catalog/step_templates"
        ids = _list_yaml_files_in_dir(catalog_dir)
        result: list[StepTemplate] = []
        for tid in ids:
            t = self.get_by_id(tid)
            if t is not None:
                result.append(t)
        return result

    def save(self, template: StepTemplate) -> None:
        pass

    def delete(self, id: str) -> None:
        pass


class YamlJobRepository:
    """Repository for job definitions: bootstrap (read-only) and tenant (ephemeral writes)."""

    def __init__(
        self,
        base: str = PRODUCT_MODEL_ROOT,
        validation_service: ValidationService | None = None,
    ) -> None:
        self._base = base
        self._validation_service = validation_service

    def set_validation_service(self, validation_service: ValidationService | None) -> None:
        """Inject validation service for save-time validation."""
        self._validation_service = validation_service

    def get_bootstrap_job(self, job_slug: str) -> JobDefinition | None:
        path = bootstrap_job_path(job_slug, self._base)
        data = load_yaml_file(path)
        if data is None:
            return None
        try:
            return parse_job_definition(data, owner_user_id_override="bootstrap")
        except (KeyError, TypeError):
            return None

    def get_by_id(self, id: str, owner_user_id: str) -> JobDefinition | None:
        # First check bootstrap
        path = bootstrap_job_path("notion_place_inserter", self._base)
        data = load_yaml_file(path)
        if data and data.get("id") == id:
            if str(data.get("status", "active")) == "archived":
                return None
            return parse_job_definition(data, owner_user_id_override=owner_user_id)
        # Tenant path: product_model/tenants/<owner>/jobs/*.yaml
        from app.domain.yaml_layout import tenant_jobs_dir

        tenant_dir = tenant_jobs_dir(owner_user_id, self._base)
        root = _project_root()
        jobs_path = root / tenant_dir
        if jobs_path.exists():
            for f in jobs_path.glob("*.yaml"):
                rel = f.relative_to(root).as_posix()
                data = load_yaml_file(rel)
                if data and data.get("id") == id:
                    if str(data.get("status", "active")) == "archived":
                        return None
                    return parse_job_definition(data, owner_user_id_override=owner_user_id)
        return None

    def get_graph_by_id(self, id: str, owner_user_id: str) -> JobGraph | None:
        """Load full job graph (job + stages + pipelines + steps) by ID for the given owner."""
        # First check bootstrap
        path = bootstrap_job_path("notion_place_inserter", self._base)
        data = load_yaml_file(path)
        if data and data.get("id") == id:
            if str(data.get("status", "active")) == "archived":
                return None
            try:
                return parse_job_graph(data, owner_user_id_override=owner_user_id)
            except (KeyError, TypeError):
                return None
        # Tenant path: product_model/tenants/<owner>/jobs/*.yaml
        from app.domain.yaml_layout import tenant_jobs_dir

        tenant_dir = tenant_jobs_dir(owner_user_id, self._base)
        root = _project_root()
        jobs_path = root / tenant_dir
        if jobs_path.exists():
            for f in jobs_path.glob("*.yaml"):
                rel = f.relative_to(root).as_posix()
                data = load_yaml_file(rel)
                if data and data.get("id") == id:
                    if str(data.get("status", "active")) == "archived":
                        return None
                    try:
                        return parse_job_graph(data, owner_user_id_override=owner_user_id)
                    except (KeyError, TypeError):
                        return None
        return None

    def list_by_owner(self, owner_user_id: str) -> list[JobDefinition]:
        result: list[JobDefinition] = []
        # Bootstrap job: same starter for all signed-in users
        path = bootstrap_job_path("notion_place_inserter", self._base)
        data = load_yaml_file(path)
        if data and str(data.get("status", "active")) != "archived":
            try:
                result.append(parse_job_definition(data, owner_user_id_override=owner_user_id))
            except (KeyError, TypeError):
                pass
        # Tenant jobs (ephemeral)
        from app.domain.yaml_layout import tenant_jobs_dir

        tenant_dir = tenant_jobs_dir(owner_user_id, self._base)
        root = _project_root()
        jobs_path = root / tenant_dir
        if jobs_path.exists():
            for f in jobs_path.glob("*.yaml"):
                rel = f.relative_to(root).as_posix()
                data = load_yaml_file(rel)
                if data and str(data.get("status", "active")) != "archived":
                    try:
                        result.append(parse_job_definition(data, owner_user_id_override=owner_user_id))
                    except (KeyError, TypeError):
                        pass
        return result

    def save(self, job: JobDefinition) -> None:
        """Persist job to tenant path. Bootstrap jobs are read-only. Use save_job_graph for full structure."""
        if job.owner_user_id == "bootstrap":
            return  # Bootstrap is read-only
        path = tenant_job_path(job.owner_user_id, job.id, self._base)
        data = domain_to_yaml_dict(job)
        data["kind"] = "job_definition"
        data["stages"] = []
        dump_yaml_file(path, data)

    def save_job_graph(
        self,
        graph: JobGraph,
        *,
        skip_reference_checks: bool = False,
    ) -> None:
        """Persist full job graph (job + stages + pipelines + steps) to tenant path."""
        if graph.job.owner_user_id == "bootstrap":
            return  # Bootstrap is read-only
        if self._validation_service:
            self._validation_service.validate_job_graph(
                graph, skip_reference_checks=skip_reference_checks
            )
        path = tenant_job_path(graph.job.owner_user_id, graph.job.id, self._base)
        data = job_graph_to_yaml_dict(graph)
        dump_yaml_file(path, data)

    def archive(self, id: str, owner_user_id: str) -> None:
        """Soft-delete: set status to archived. Archived jobs are excluded from list and get_graph_by_id."""
        if owner_user_id == "bootstrap":
            return  # Bootstrap is read-only
        path = tenant_job_path(owner_user_id, id, self._base)
        root = _project_root()
        full_path = root / path
        if not full_path.exists():
            return
        data = load_yaml_file(path)
        if data is None:
            return
        data["status"] = "archived"
        dump_yaml_file(path, data)

    def delete(self, id: str, owner_user_id: str) -> None:
        """Remove job file from tenant path."""
        path = tenant_job_path(owner_user_id, id, self._base)
        root = _project_root()
        full_path = root / path
        if full_path.exists():
            full_path.unlink()


class YamlTriggerRepository:
    """Owner-scoped repository for trigger definitions."""

    def __init__(
        self,
        base: str = PRODUCT_MODEL_ROOT,
        validation_service: ValidationService | None = None,
    ) -> None:
        self._base = base
        self._validation_service = validation_service

    def set_validation_service(self, validation_service: ValidationService | None) -> None:
        """Inject validation service for save-time validation."""
        self._validation_service = validation_service

    def get_by_id(self, id: str, owner_user_id: str) -> TriggerDefinition | None:
        if owner_user_id == "bootstrap":
            file_path = bootstrap_trigger_path(id, self._base)
            data = load_yaml_file(file_path)
            if data is None:
                return None
            try:
                return parse_trigger_definition(data)
            except (KeyError, TypeError):
                return None
        # Tenant path first, then fall back to bootstrap (matches get_by_path behavior)
        path = tenant_trigger_path(owner_user_id, id, self._base)
        data = load_yaml_file(path)
        if data is not None:
            try:
                return parse_trigger_definition(data)
            except (KeyError, TypeError):
                pass
        # Fall back to bootstrap triggers
        file_path = bootstrap_trigger_path(id, self._base)
        data = load_yaml_file(file_path)
        if data is None:
            return None
        try:
            return parse_trigger_definition(data)
        except (KeyError, TypeError):
            return None

    def _path_for_load(self, f: Path, root: Path) -> str:
        """Path for load_yaml_file: relative if under root, else absolute."""
        try:
            return f.relative_to(root).as_posix()
        except ValueError:
            return str(f)

    def get_by_path(self, path: str, owner_user_id: str) -> TriggerDefinition | None:
        root = _project_root()
        # Tenant triggers first
        triggers_dir = root / tenant_triggers_dir(owner_user_id, self._base)
        if triggers_dir.exists():
            for f in triggers_dir.glob("*.yaml"):
                data = load_yaml_file(self._path_for_load(f, root))
                if data and data.get("path") == path:
                    try:
                        return parse_trigger_definition(data)
                    except (KeyError, TypeError):
                        pass
        # Bootstrap triggers
        bootstrap_dir = root / f"{self._base}/bootstrap/triggers"
        if bootstrap_dir.exists():
            for f in bootstrap_dir.glob("*.yaml"):
                data = load_yaml_file(self._path_for_load(f, root))
                if data and data.get("path") == path:
                    try:
                        return parse_trigger_definition(data)
                    except (KeyError, TypeError):
                        pass
        return None

    def list_by_owner(self, owner_user_id: str) -> list[TriggerDefinition]:
        root = _project_root()
        result: list[TriggerDefinition] = []
        if owner_user_id == "bootstrap":
            bootstrap_dir = root / f"{self._base}/bootstrap/triggers"
            if bootstrap_dir.exists():
                for f in bootstrap_dir.glob("*.yaml"):
                    data = load_yaml_file(self._path_for_load(f, root))
                    if data:
                        try:
                            result.append(parse_trigger_definition(data))
                        except (KeyError, TypeError):
                            pass
            return result
        triggers_dir = root / tenant_triggers_dir(owner_user_id, self._base)
        if not triggers_dir.exists():
            return []
        for f in triggers_dir.glob("*.yaml"):
            data = load_yaml_file(self._path_for_load(f, root))
            if data:
                try:
                    result.append(parse_trigger_definition(data))
                except (KeyError, TypeError):
                    pass
        return result

    def save(self, trigger: TriggerDefinition) -> None:
        if self._validation_service:
            self._validation_service.validate_trigger(trigger)
        path = tenant_trigger_path(trigger.owner_user_id, trigger.id, self._base)
        data = domain_to_yaml_dict(trigger)
        dump_yaml_file(path, data)

    def delete(self, id: str, owner_user_id: str) -> None:
        path = tenant_trigger_path(owner_user_id, id, self._base)
        root = _project_root()
        full_path = root / path
        if full_path.exists():
            full_path.unlink()


class YamlTargetRepository:
    """Owner-scoped repository for data targets."""

    def __init__(
        self,
        base: str = PRODUCT_MODEL_ROOT,
        validation_service: ValidationService | None = None,
    ) -> None:
        self._base = base
        self._validation_service = validation_service

    def set_validation_service(self, validation_service: ValidationService | None) -> None:
        """Inject validation service for save-time validation."""
        self._validation_service = validation_service

    def get_by_id(self, id: str, owner_user_id: str) -> DataTarget | None:
        path = tenant_target_path(owner_user_id, id, self._base)
        data = load_yaml_file(path)
        if data is None:
            return None
        try:
            return parse_data_target(data)
        except (KeyError, TypeError):
            return None

    def list_by_owner(self, owner_user_id: str) -> list[DataTarget]:
        root = _project_root()
        targets_dir = root / tenant_targets_dir(owner_user_id, self._base)
        if not targets_dir.exists():
            return []
        result: list[DataTarget] = []
        for f in targets_dir.glob("*.yaml"):
            data = load_yaml_file(f.relative_to(root).as_posix())
            if data:
                try:
                    result.append(parse_data_target(data))
                except (KeyError, TypeError):
                    pass
        return result

    def save(self, target: DataTarget) -> None:
        if self._validation_service:
            self._validation_service.validate_data_target(target)
        path = tenant_target_path(target.owner_user_id, target.id, self._base)
        data = domain_to_yaml_dict(target)
        dump_yaml_file(path, data)

    def delete(self, id: str, owner_user_id: str) -> None:
        path = tenant_target_path(owner_user_id, id, self._base)
        root = _project_root()
        full_path = root / path
        if full_path.exists():
            full_path.unlink()


class YamlTargetSchemaRepository:
    """Owner-scoped repository for target schema snapshots."""

    def __init__(self, base: str = PRODUCT_MODEL_ROOT) -> None:
        self._base = base

    def get_by_id(self, id: str, owner_user_id: str) -> TargetSchemaSnapshot | None:
        path = tenant_target_schema_snapshot_path(owner_user_id, id, self._base)
        data = load_yaml_file(path)
        if data is None:
            return None
        try:
            return parse_target_schema_snapshot(data)
        except (KeyError, TypeError):
            return None

    def list_by_owner(self, owner_user_id: str) -> list[TargetSchemaSnapshot]:
        root = _project_root()
        snap_dir = root / tenant_target_schema_snapshots_dir(owner_user_id, self._base)
        if not snap_dir.exists():
            return []
        result: list[TargetSchemaSnapshot] = []
        for f in snap_dir.glob("*.yaml"):
            data = load_yaml_file(f.relative_to(root).as_posix())
            if data:
                try:
                    result.append(parse_target_schema_snapshot(data))
                except (KeyError, TypeError):
                    pass
        return result

    def get_active_for_target(
        self, data_target_id: str, owner_user_id: str
    ) -> TargetSchemaSnapshot | None:
        for snap in self.list_by_owner(owner_user_id):
            if snap.data_target_id == data_target_id and snap.is_active:
                return snap
        return None

    def save(self, snapshot: TargetSchemaSnapshot) -> None:
        path = tenant_target_schema_snapshot_path(
            snapshot.owner_user_id, snapshot.id, self._base
        )
        data = domain_to_yaml_dict(snapshot)
        dump_yaml_file(path, data)

    def delete(self, id: str, owner_user_id: str) -> None:
        path = tenant_target_schema_snapshot_path(owner_user_id, id, self._base)
        root = _project_root()
        full_path = root / path
        if full_path.exists():
            full_path.unlink()


class YamlConnectorInstanceRepository:
    """Owner-scoped repository for connector instances."""

    def __init__(self, base: str = PRODUCT_MODEL_ROOT) -> None:
        self._base = base

    def get_by_id(self, id: str, owner_user_id: str) -> ConnectorInstance | None:
        path = tenant_connector_instance_path(owner_user_id, id, self._base)
        data = load_yaml_file(path)
        if data is None:
            return None
        try:
            return parse_connector_instance(data)
        except (KeyError, TypeError):
            return None

    def list_by_owner(self, owner_user_id: str) -> list[ConnectorInstance]:
        root = _project_root()
        inst_dir = root / tenant_connector_instances_dir(owner_user_id, self._base)
        if not inst_dir.exists():
            return []
        result: list[ConnectorInstance] = []
        for f in inst_dir.glob("*.yaml"):
            data = load_yaml_file(f.relative_to(root).as_posix())
            if data:
                try:
                    result.append(parse_connector_instance(data))
                except (KeyError, TypeError):
                    pass
        return result

    def save(self, instance: ConnectorInstance) -> None:
        path = tenant_connector_instance_path(
            instance.owner_user_id, instance.id, self._base
        )
        data = domain_to_yaml_dict(instance)
        dump_yaml_file(path, data)

    def delete(self, id: str, owner_user_id: str) -> None:
        path = tenant_connector_instance_path(owner_user_id, id, self._base)
        root = _project_root()
        full_path = root / path
        if full_path.exists():
            full_path.unlink()


class YamlAppConfigRepository:
    """Owner-scoped repository for app config (limits)."""

    def __init__(self, base: str = PRODUCT_MODEL_ROOT) -> None:
        self._base = base

    def get_by_owner(self, owner_user_id: str) -> AppLimits | None:
        path = tenant_app_config_path(owner_user_id, self._base)
        data = load_yaml_file(path)
        if data is None:
            return None
        try:
            return parse_app_limits(data)
        except (KeyError, TypeError):
            return None

    def save(self, owner_user_id: str, limits: AppLimits) -> None:
        path = tenant_app_config_path(owner_user_id, self._base)
        data = domain_to_yaml_dict(limits)
        dump_yaml_file(path, data)
