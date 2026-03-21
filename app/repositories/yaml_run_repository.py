"""YAML-backed RunRepository implementation for Phase 3."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from loguru import logger

from app.domain.runs import (
    JobRun,
    PipelineRun,
    StageRun,
    StepRun,
    UsageRecord,
)
from app.domain.yaml_layout import (
    PRODUCT_MODEL_ROOT,
    tenant_job_run_path,
    tenant_pipeline_run_path,
    tenant_runs_dir,
    tenant_stage_run_path,
    tenant_step_run_path,
    tenant_usage_record_path,
)
from app.repositories.yaml_loader import (
    dump_yaml_file,
    load_yaml_file,
    parse_job_run,
    parse_pipeline_run,
    parse_stage_run,
    parse_step_run,
    parse_usage_record,
)
from app.repositories.yaml_loader import domain_to_yaml_dict


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _find_owner_for_job_run(base: str, job_run_id: str) -> str:
    """Find owner_user_id by scanning tenant runs for a job run file."""
    root = _project_root()
    tenants_dir = root / base / "tenants"
    if not tenants_dir.exists():
        return ""
    for tenant_dir in tenants_dir.iterdir():
        if tenant_dir.is_dir():
            run_file = tenant_dir / "runs" / f"{job_run_id}.yaml"
            if run_file.exists():
                return tenant_dir.name
    return ""


def _find_job_run_by_id(repo: "YamlRunRepository", run_id: str) -> JobRun | None:
    """Find JobRun by id by scanning all tenant run dirs."""
    root = _project_root()
    tenants_dir = root / repo._base / "tenants"
    if not tenants_dir.exists():
        return None
    for tenant_dir in tenants_dir.iterdir():
        if tenant_dir.is_dir():
            run = repo.get_job_run(run_id, tenant_dir.name)
            if run:
                return run
    return None


class YamlRunRepository:
    """YAML-backed repository for job runs and nested run records.

    Stores JobRun at tenants/<owner>/runs/<run_id>.yaml.
    Stage/Pipeline/Step runs and usage records under nested dirs.
    Ephemeral: container-local, not durable across restarts.
    """

    def __init__(self, base: str = PRODUCT_MODEL_ROOT) -> None:
        self._base = base

    def get_job_run(self, id: str, owner_user_id: str) -> JobRun | None:
        path = tenant_job_run_path(owner_user_id, id, self._base)
        data = load_yaml_file(path)
        if data is None:
            return None
        try:
            return parse_job_run(data)
        except (KeyError, TypeError):
            return None

    def get_job_run_by_platform_job_id(
        self, platform_job_id: str, owner_user_id: str
    ) -> JobRun | None:
        runs = self.list_job_runs_by_owner(owner_user_id, limit=500)
        for run in runs:
            if run.platform_job_id == platform_job_id:
                return run
        return None

    def list_job_runs_by_owner(
        self,
        owner_user_id: str,
        *,
        job_id: str | None = None,
        limit: int = 100,
    ) -> list[JobRun]:
        root = _project_root()
        runs_dir = root / tenant_runs_dir(owner_user_id, self._base)
        if not runs_dir.exists() or not runs_dir.is_dir():
            return []
        result: list[JobRun] = []
        for f in runs_dir.iterdir():
            if f.is_file() and f.suffix == ".yaml":
                try:
                    rel = f.relative_to(root).as_posix()
                except ValueError:
                    rel = str(f)
                data = load_yaml_file(rel)
                if data is None:
                    continue
                try:
                    run = parse_job_run(data)
                    if job_id is not None and run.job_id != job_id:
                        continue
                    result.append(run)
                except (KeyError, TypeError):
                    continue
        result.sort(
            key=lambda r: (r.started_at or r.completed_at or ""),
            reverse=True,
        )
        return result[:limit]

    def list_step_runs_for_job_run(
        self, job_run_id: str, owner_user_id: str
    ) -> list[StepRun]:
        """Load all step run YAML files under the job run tree (local dev / YAML repo)."""
        root = _project_root()
        base_dir = root / tenant_runs_dir(owner_user_id, self._base) / job_run_id / "stages"
        if not base_dir.exists() or not base_dir.is_dir():
            return []
        result: list[StepRun] = []
        for stage_dir in sorted(base_dir.iterdir()):
            if not stage_dir.is_dir():
                continue
            stage_run_id = stage_dir.name
            pipelines_dir = stage_dir / "pipelines"
            if not pipelines_dir.exists():
                continue
            for pipe_dir in sorted(pipelines_dir.iterdir()):
                if not pipe_dir.is_dir():
                    continue
                pipeline_run_id = pipe_dir.name
                pipeline_rel = tenant_pipeline_run_path(
                    owner_user_id,
                    job_run_id,
                    stage_run_id,
                    pipeline_run_id,
                    self._base,
                )
                pdata = load_yaml_file(pipeline_rel)
                pipeline_id = ""
                if pdata:
                    try:
                        pipeline_id = parse_pipeline_run(pdata).pipeline_id
                    except (KeyError, TypeError):
                        pipeline_id = ""
                steps_dir = pipe_dir / "steps"
                if not steps_dir.exists():
                    continue
                for step_file in sorted(steps_dir.glob("*.yaml")):
                    try:
                        rel = step_file.relative_to(root).as_posix()
                    except ValueError:
                        rel = str(step_file)
                    sdata = load_yaml_file(rel)
                    if sdata is None:
                        continue
                    try:
                        sr = parse_step_run(sdata)
                        result.append(
                            replace(sr, pipeline_id=pipeline_id or None)
                        )
                    except (KeyError, TypeError):
                        continue
        result.sort(
            key=lambda s: (s.started_at or s.completed_at or ""),
        )
        return result

    def save_job_run(self, run: JobRun) -> None:
        path = tenant_job_run_path(run.owner_user_id, run.id, self._base)
        data = domain_to_yaml_dict(run)
        data["kind"] = "job_run"
        try:
            dump_yaml_file(path, data)
        except Exception as e:
            logger.exception(
                "yaml_run_repository_save_job_run_failed | run_id={} owner={} error={}",
                run.id,
                run.owner_user_id,
                e,
            )
            raise

    def save_stage_run(self, run: StageRun) -> None:
        owner = run.owner_user_id or _find_owner_for_job_run(self._base, run.job_run_id)
        path = tenant_stage_run_path(owner, run.job_run_id, run.id, self._base)
        data = domain_to_yaml_dict(run)
        data["kind"] = "stage_run"
        try:
            dump_yaml_file(path, data)
        except Exception as e:
            logger.exception(
                "yaml_run_repository_save_stage_run_failed | stage_run_id={} job_run_id={} error={}",
                run.id,
                run.job_run_id,
                e,
            )
            raise

    def save_pipeline_run(self, run: PipelineRun) -> None:
        owner = run.owner_user_id or _find_owner_for_job_run(
            self._base, run.job_run_id or run.stage_run_id
        )
        job_run_id = run.job_run_id
        if not job_run_id:
            stage_run = self._load_stage_run(run.stage_run_id, owner)
            job_run_id = stage_run.job_run_id if stage_run else run.stage_run_id
        path = tenant_pipeline_run_path(
            owner, job_run_id, run.stage_run_id, run.id, self._base
        )
        data = domain_to_yaml_dict(run)
        data["kind"] = "pipeline_run"
        try:
            dump_yaml_file(path, data)
        except Exception as e:
            logger.exception(
                "yaml_run_repository_save_pipeline_run_failed | pipeline_run_id={} error={}",
                run.id,
                e,
            )
            raise

    def _load_stage_run(self, stage_run_id: str, owner: str) -> StageRun | None:
        root = _project_root()
        runs_dir = root / tenant_runs_dir(owner, self._base)
        if not runs_dir.exists():
            return None
        for job_run_dir in runs_dir.iterdir():
            if job_run_dir.is_dir():
                stages_dir = job_run_dir / "stages"
                stage_file = stages_dir / f"{stage_run_id}.yaml"
                if stage_file.exists():
                    rel = stage_file.relative_to(root).as_posix()
                    data = load_yaml_file(rel)
                    if data:
                        return parse_stage_run(data)
        return None

    def save_step_run(self, run: StepRun) -> None:
        owner = run.owner_user_id or _find_owner_for_job_run(
            self._base, run.job_run_id or run.pipeline_run_id
        )
        pipeline_run = self._load_pipeline_run(run.pipeline_run_id, owner)
        job_run_id = run.job_run_id
        stage_run_id = run.stage_run_id
        if pipeline_run:
            job_run_id = job_run_id or pipeline_run.job_run_id
            stage_run_id = stage_run_id or pipeline_run.stage_run_id
            if not job_run_id:
                stage_run = self._load_stage_run(pipeline_run.stage_run_id, owner)
                if stage_run:
                    job_run_id = stage_run.job_run_id
                    stage_run_id = pipeline_run.stage_run_id
        if not job_run_id:
            job_run_id = run.pipeline_run_id
        if not stage_run_id and pipeline_run:
            stage_run_id = pipeline_run.stage_run_id
        path = tenant_step_run_path(
            owner, job_run_id, stage_run_id, run.pipeline_run_id, run.id, self._base
        )
        data = domain_to_yaml_dict(run)
        data["kind"] = "step_run"
        try:
            dump_yaml_file(path, data)
        except Exception as e:
            logger.exception(
                "yaml_run_repository_save_step_run_failed | step_run_id={} error={}",
                run.id,
                e,
            )
            raise

    def _load_pipeline_run(self, pipeline_run_id: str, owner: str) -> PipelineRun | None:
        root = _project_root()
        runs_dir = root / tenant_runs_dir(owner, self._base)
        if not runs_dir.exists():
            return None
        for job_run_dir in runs_dir.iterdir():
            if job_run_dir.is_dir():
                stages_dir = job_run_dir / "stages"
                if stages_dir.exists():
                    for stage_dir in stages_dir.iterdir():
                        if stage_dir.is_dir():
                            pipelines_dir = stage_dir / "pipelines"
                            pipe_file = pipelines_dir / f"{pipeline_run_id}.yaml"
                            if pipe_file.exists():
                                rel = pipe_file.relative_to(root).as_posix()
                                data = load_yaml_file(rel)
                                if data:
                                    return parse_pipeline_run(data)
        return None

    def save_usage_record(self, record: UsageRecord) -> None:
        owner = record.owner_user_id or _find_owner_for_job_run(
            self._base, record.job_run_id
        )
        path = tenant_usage_record_path(
            owner, record.job_run_id, record.id, self._base
        )
        data = domain_to_yaml_dict(record)
        data["kind"] = "usage_record"
        try:
            dump_yaml_file(path, data)
        except Exception as e:
            logger.exception(
                "yaml_run_repository_save_usage_record_failed | record_id={} job_run_id={} error={}",
                record.id,
                record.job_run_id,
                e,
            )
            raise
