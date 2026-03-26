"""Postgres bootstrap provisioning: catalog seed and lazy owner starter definitions."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from supabase import AsyncClient

from app.domain import (
    ConnectorInstance,
    ConnectorTemplate,
    DataTarget,
    TriggerDefinition,
)
from app.domain.yaml_layout import (
    PRODUCT_MODEL_ROOT,
    bootstrap_job_path,
    bootstrap_trigger_path,
    catalog_connector_template_path,
    catalog_step_template_path,
    catalog_target_template_path,
)
from app.domain.repositories import TriggerJobLinkRepository
from app.repositories.postgres_repositories import (
    PostgresAppConfigRepository,
    PostgresConnectorInstanceRepository,
    PostgresConnectorTemplateRepository,
    PostgresJobRepository,
    PostgresTargetRepository,
    PostgresTargetTemplateRepository,
    PostgresStepTemplateRepository,
    PostgresTriggerRepository,
    _ensure_uuid,
)
from app.repositories.yaml_loader import (
    load_yaml_file,
    parse_connector_template,
    parse_job_graph,
    parse_step_template,
    parse_target_template,
    parse_trigger_definition,
)

USAGE_PROVIDERS_CATALOG_YAML = "product_model/catalog/usage_providers.yaml"

# Starter definitions derived from bootstrap YAML
STARTER_TRIGGER_PATH = "/locations"
STARTER_JOB_SLUG = "notion_place_inserter"
STARTER_JOB_ID = "job_notion_place_inserter"
# Dev/local only: real Places to Visit data source ID for bootstrap target.
# TODO: Before production, replace with per-tenant resolution (e.g. OAuth binding,
#       user-selected DB, or env override) — this value must not be hardcoded.
PLACEHOLDER_EXTERNAL_TARGET_ID = "9592d56b-899e-440e-9073-b2f0768669ad"
# Placeholder for Locations target until user selects via OAuth. Same convention as above.
PLACEHOLDER_LOCATIONS_EXTERNAL_TARGET_ID = "cfecaf05-306e-48ac-9d8b-bb14e8243d44"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _list_catalog_ids(relative_dir: str) -> list[str]:
    root = _project_root()
    dir_path = root / relative_dir
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    return [f.stem for f in dir_path.glob("*.yaml")]


class PostgresBootstrapProvisioningService:
    """
    Bootstrap provisioning implementation. All YAML->Postgres mapping lives here.
    No direct bootstrap YAML parsing from routes, worker, or repositories.
    """

    def __init__(self, client: AsyncClient, link_repo: TriggerJobLinkRepository) -> None:
        self._client = client
        self._link_repo = link_repo
        self._connector_templates = PostgresConnectorTemplateRepository(client)
        self._target_templates = PostgresTargetTemplateRepository(client)
        self._step_templates = PostgresStepTemplateRepository(client)
        self._connector_instances = PostgresConnectorInstanceRepository(client)
        self._targets = PostgresTargetRepository(client)
        self._triggers = PostgresTriggerRepository(client)
        self._jobs = PostgresJobRepository(client)
        self._app_config = PostgresAppConfigRepository(client)

    async def seed_catalog_if_needed(self) -> None:
        """Idempotently seed connector, target, and step templates from catalog YAML."""
        for tid in _list_catalog_ids(f"{PRODUCT_MODEL_ROOT}/catalog/connector_templates"):
            path = catalog_connector_template_path(tid, PRODUCT_MODEL_ROOT)
            data = load_yaml_file(path)
            if data:
                try:
                    t = parse_connector_template(data)
                    await self._connector_templates.save(t)
                    logger.debug("bootstrap_seed_connector_template | id={}", tid)
                except (KeyError, TypeError) as e:
                    logger.warning("bootstrap_skip_connector_template | id={} error={}", tid, e)

        for tid in _list_catalog_ids(f"{PRODUCT_MODEL_ROOT}/catalog/target_templates"):
            path = catalog_target_template_path(tid, PRODUCT_MODEL_ROOT)
            data = load_yaml_file(path)
            if data:
                try:
                    t = parse_target_template(data)
                    await self._target_templates.save(t)
                    logger.debug("bootstrap_seed_target_template | id={}", tid)
                except (KeyError, TypeError) as e:
                    logger.warning("bootstrap_skip_target_template | id={} error={}", tid, e)

        for tid in _list_catalog_ids(f"{PRODUCT_MODEL_ROOT}/catalog/step_templates"):
            path = catalog_step_template_path(tid, PRODUCT_MODEL_ROOT)
            data = load_yaml_file(path)
            if data:
                try:
                    t = parse_step_template(data)
                    await self._step_templates.save(t)
                    logger.debug("bootstrap_seed_step_template | id={}", tid)
                except (KeyError, TypeError) as e:
                    logger.warning("bootstrap_skip_step_template | id={} error={}", tid, e)

        await self._seed_usage_provider_definitions_from_yaml()

        logger.info("bootstrap_seed_catalog_complete")

    async def _seed_usage_provider_definitions_from_yaml(self) -> None:
        """Upsert built-in usage provider labels from version-controlled YAML."""
        data = load_yaml_file(USAGE_PROVIDERS_CATALOG_YAML)
        if not data:
            logger.debug("bootstrap_skip_usage_providers | missing_or_empty_yaml")
            return
        providers = data.get("providers")
        if not isinstance(providers, list):
            return
        for p in providers:
            if not isinstance(p, dict):
                continue
            pid = p.get("provider_id")
            if not pid or not isinstance(pid, str):
                continue
            row = {
                "provider_id": pid,
                "display_name": p.get("display_name") or pid,
                "description": (p.get("description") or "") if isinstance(p.get("description"), str) else "",
                "billing_unit": (p.get("billing_unit") or "call")
                if isinstance(p.get("billing_unit"), str)
                else "call",
                "notes": p.get("notes") if isinstance(p.get("notes"), str) else None,
            }
            try:
                await self._client.table("usage_provider_definitions").upsert(
                    row, on_conflict="provider_id"
                ).execute()
                logger.debug("bootstrap_seed_usage_provider | id={}", pid)
            except Exception as e:
                logger.warning("bootstrap_skip_usage_provider | id={} error={}", pid, e)

    async def _provision_owner_starter_definitions(self, owner_user_id: str, uid: str) -> None:
        """
        Load starter YAML and upsert connector instances, targets, job graph, trigger, and link.
        Caller must ensure starter trigger/job rows are absent or intended to be replaced.
        """
        # Load bootstrap YAML
        trigger_data = load_yaml_file(bootstrap_trigger_path("trigger_http_locations", PRODUCT_MODEL_ROOT))
        job_data = load_yaml_file(bootstrap_job_path(STARTER_JOB_SLUG, PRODUCT_MODEL_ROOT))
        if not trigger_data or not job_data:
            logger.warning("bootstrap_ensure_owner_missing_yaml | owner={}", owner_user_id)
            return

        # 1. Connector instances (required by target and job steps)
        for conn_id, template_id in [
            ("connector_instance_google_places_default", "google_places_api"),
            ("connector_instance_notion_default", "notion_oauth_workspace"),
        ]:
            if not await self._connector_instances.get_by_id(conn_id, uid):
                inst = ConnectorInstance(
                    id=conn_id,
                    owner_user_id=uid,
                    connector_template_id=template_id,
                    display_name=conn_id.replace("connector_instance_", "").replace("_", " ").title(),
                    status="active",
                    config={},
                    secret_ref=None,
                    visibility="owner",
                )
                await self._connector_instances.save(inst)
                logger.info("bootstrap_provision_connector | id={} owner={}", conn_id, owner_user_id)

        # 2. Targets (required by job and ai_select_relation)
        for target_id, display_name, placeholder_id in [
            ("target_places_to_visit", "Places to Visit", PLACEHOLDER_EXTERNAL_TARGET_ID),
            ("target_locations", "Locations", PLACEHOLDER_LOCATIONS_EXTERNAL_TARGET_ID),
        ]:
            if not await self._targets.get_by_id(target_id, uid):
                target = DataTarget(
                    id=target_id,
                    owner_user_id=uid,
                    target_template_id="notion_database",
                    connector_instance_id="connector_instance_notion_default",
                    display_name=display_name,
                    external_target_id=placeholder_id,
                    status="active",
                    visibility="owner",
                )
                await self._targets.save(target)
                logger.info("bootstrap_provision_target | id={} owner={}", target_id, owner_user_id)

        # 3. Parse trigger to get trigger_id for job wiring
        trigger = parse_trigger_definition(trigger_data)
        trigger.owner_user_id = uid
        trigger.secret_value = secrets.token_hex(15)  # ~30 chars
        trigger.secret_last_rotated_at = datetime.now(timezone.utc)

        # 4. Job graph first (job must exist before trigger; linkage via trigger_job_links)
        graph = parse_job_graph(job_data, owner_user_id_override=uid)
        graph.job.owner_user_id = uid
        # target_id comes from YAML (e.g. target_places_to_visit); do not overwrite with unrelated ids

        # Ensure all step templates referenced by the bootstrap graph exist.
        # This protects owner provisioning when catalog seeding is partial.
        for template_id in sorted({step.step_template_id for step in graph.steps}):
            if await self._step_templates.get_by_id(template_id):
                continue
            template_data = load_yaml_file(catalog_step_template_path(template_id, PRODUCT_MODEL_ROOT))
            if not template_data:
                logger.warning(
                    "bootstrap_missing_step_template | id={} owner={}",
                    template_id,
                    owner_user_id,
                )
                continue
            template = parse_step_template(template_data)
            await self._step_templates.save(template)
            logger.info("bootstrap_provision_step_template | id={} owner={}", template_id, owner_user_id)

        await self._jobs.save_job_graph(graph, skip_reference_checks=True)
        logger.info("bootstrap_provision_job | id={} owner={}", graph.job.id, owner_user_id)

        # 5. Trigger (after job so link can reference both)
        await self._triggers.save(trigger)
        logger.info("bootstrap_provision_trigger | id={} owner={}", trigger.id, owner_user_id)

        # 6. Link trigger to job (many-to-many)
        await self._link_repo.attach(trigger.id, graph.job.id, uid)
        logger.info("bootstrap_provision_link | trigger_id={} job_id={} owner={}", trigger.id, graph.job.id, owner_user_id)

    async def ensure_owner_starter_definitions(self, owner_user_id: str) -> None:
        """
        Ensure owner has starter definitions. Idempotent.
        Provisions connector instances, target, trigger, job graph from bootstrap YAML if missing.
        """
        try:
            uid = str(_ensure_uuid(owner_user_id))
        except ValueError:
            logger.warning("bootstrap_ensure_owner_skipped | invalid_owner={}", owner_user_id)
            return

        await self._app_config.seed_user_limits_from_defaults_if_missing(owner_user_id)

        trigger = await self._triggers.get_by_path(STARTER_TRIGGER_PATH, uid)
        if trigger:
            logger.debug("bootstrap_ensure_owner_already_provisioned | owner={}", owner_user_id)
            return

        await self._provision_owner_starter_definitions(owner_user_id, uid)

    async def reprovision_owner_starter_definitions(self, owner_user_id: str) -> None:
        """
        Tear down the starter HTTP trigger (path ``/locations``) and starter job graph, then
        re-import from bundled YAML. **Destructive** for the Notion Place Inserter starter job
        and its trigger; connector instances and targets are left in place.

        Use after updating ``product_model/bootstrap/jobs/notion_place_inserter.yaml`` (and trigger
        YAML) so the next provision matches repo state.
        """
        try:
            uid = str(_ensure_uuid(owner_user_id))
        except ValueError:
            logger.warning("bootstrap_reprovision_skipped | invalid_owner={}", owner_user_id)
            return

        existing_trigger = await self._triggers.get_by_path(STARTER_TRIGGER_PATH, uid)
        if existing_trigger:
            await self._triggers.delete(existing_trigger.id, uid)
            logger.info(
                "bootstrap_reprovision_deleted_trigger | id={} owner={}",
                existing_trigger.id,
                owner_user_id,
            )

        if await self._jobs.get_graph_by_id(STARTER_JOB_ID, uid):
            await self._jobs.delete(STARTER_JOB_ID, uid)
            logger.info("bootstrap_reprovision_deleted_job | id={} owner={}", STARTER_JOB_ID, owner_user_id)

        await self._provision_owner_starter_definitions(owner_user_id, uid)
