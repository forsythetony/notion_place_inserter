"""Repository implementations for Phase 3 (YAML) and Phase 4 (Postgres) product model."""

from app.repositories.yaml_loader import (
    load_yaml_file,
    parse_connector_template,
    parse_job_definition,
    parse_job_graph,
    parse_step_template,
    parse_target_template,
)
from app.repositories.yaml_repositories import (
    YamlAppConfigRepository,
    YamlConnectorInstanceRepository,
    YamlConnectorTemplateRepository,
    YamlJobRepository,
    YamlStepTemplateRepository,
    YamlTargetSchemaRepository,
    YamlTargetTemplateRepository,
    YamlTargetRepository,
    YamlTriggerRepository,
)
from app.repositories.yaml_run_repository import YamlRunRepository
from app.repositories.postgres_repositories import (
    PostgresAppConfigRepository,
    PostgresConnectorInstanceRepository,
    PostgresConnectorTemplateRepository,
    PostgresJobRepository,
    PostgresStepTemplateRepository,
    PostgresTargetRepository,
    PostgresTargetSchemaRepository,
    PostgresTargetTemplateRepository,
    PostgresTriggerRepository,
)
from app.repositories.postgres_run_repository import PostgresRunRepository

__all__ = [
    "load_yaml_file",
    "parse_connector_template",
    "parse_job_definition",
    "parse_job_graph",
    "parse_step_template",
    "parse_target_template",
    "YamlAppConfigRepository",
    "YamlConnectorInstanceRepository",
    "YamlConnectorTemplateRepository",
    "YamlJobRepository",
    "YamlStepTemplateRepository",
    "YamlTargetSchemaRepository",
    "YamlTargetTemplateRepository",
    "YamlTargetRepository",
    "YamlTriggerRepository",
    "YamlRunRepository",
    "PostgresAppConfigRepository",
    "PostgresConnectorInstanceRepository",
    "PostgresConnectorTemplateRepository",
    "PostgresJobRepository",
    "PostgresStepTemplateRepository",
    "PostgresTargetRepository",
    "PostgresTargetSchemaRepository",
    "PostgresTargetTemplateRepository",
    "PostgresTriggerRepository",
    "PostgresRunRepository",
]
