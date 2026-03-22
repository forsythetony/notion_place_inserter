"""Trigger and locations API routes."""

import hmac
import os
import uuid
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, Request
from loguru import logger

from app.dependencies import _extract_bearer_token
from app.services.run_quota import RunQuotaExceeded
from app.services.trigger_request_body import (
    build_trigger_payload,
    debug_payload_json_for_logging,
    preview_string_for_log,
    validate_request_body_against_schema,
)

router = APIRouter()

# Legacy /places path (no trigger row): still validates a single ``keywords`` string.
KEYWORDS_MAX_LENGTH = 300


def _job_id() -> str:
    """Generate job_id in format loc_<hex>."""
    return f"loc_{uuid.uuid4().hex}"


def _normalize_trigger_path(path: str) -> str:
    """Ensure path has leading slash for trigger resolution."""
    p = (path or "").strip()
    return f"/{p}" if p and not p.startswith("/") else p or "/"


def _linked_and_dispatchable_job_ids(link_repo, trigger_id: str, user_id: str) -> tuple[list[str], list[str]]:
    linked = link_repo.list_job_ids_for_trigger(trigger_id, user_id)
    dispatchable = link_repo.list_dispatchable_job_ids_for_trigger(trigger_id, user_id)
    return linked, dispatchable


def _ensure_trigger_has_dispatchable_jobs(
    linked_job_ids: list[str],
    dispatchable_job_ids: list[str],
) -> None:
    if not linked_job_ids:
        raise HTTPException(
            status_code=422,
            detail="Trigger is not linked to a pipeline. Assign this trigger to a pipeline before invoking.",
        )
    if not dispatchable_job_ids:
        raise HTTPException(
            status_code=422,
            detail=(
                "Trigger is linked only to disabled or archived pipelines. "
                "Enable at least one pipeline before invoking."
            ),
        )


def _validate_trigger_secret(authorization: str | None, expected_secret: str) -> None:
    """Validate Authorization: Bearer <secret> against expected trigger secret. Raises 401 if invalid."""
    token = _extract_bearer_token(authorization)
    if not token or not expected_secret or not hmac.compare_digest(token, expected_secret):
        logger.warning("trigger_auth_rejected | reason=missing_or_invalid_bearer_secret")
        raise HTTPException(status_code=401, detail="Unauthorized")


def _validate_legacy_secret(authorization: str | None) -> None:
    """Validate Authorization against env SECRET for legacy fallback path (no trigger). Raises 401 if invalid."""
    secret = os.environ.get("SECRET", "")
    if not secret:
        logger.error("SECRET environment variable is not set")
        raise HTTPException(status_code=500, detail="Server misconfiguration")
    token = _extract_bearer_token(authorization)
    if not token or not hmac.compare_digest(token, secret):
        logger.warning("trigger_auth_rejected | reason=missing_or_invalid_legacy_secret")
        raise HTTPException(status_code=401, detail="Unauthorized")


def _validate_and_build_trigger_payload(trigger, body: dict[str, Any]) -> dict[str, Any]:
    """Validate JSON body against the trigger's ``request_body_schema``; return ``trigger_payload``."""
    try:
        validated = validate_request_body_against_schema(body, trigger.request_body_schema)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return build_trigger_payload(validated, trigger.request_body_schema)


def _legacy_keywords_from_body(body: dict[str, Any]) -> str:
    """Single string field used by legacy PlacesService path (no trigger row)."""
    kw = body.get("keywords")
    if isinstance(kw, str) and kw.strip():
        return kw.strip()
    raise HTTPException(
        status_code=400,
        detail="keywords is required and cannot be empty. Use POST /test/randomLocation for random test entries.",
    )


@router.post("/triggers/{user_id}/{path:path}")
def invoke_trigger(
    request: Request,
    user_id: str,
    path: str,
    body: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    """
    Invoke an HTTP trigger by user and path.
    Auth: Authorization: Bearer <trigger_secret> (per-trigger secret from DB).
    Request JSON must match that trigger's ``request_body_schema`` (field names and types).
    When async is enabled, returns immediately with job_id; pipeline runs in background.
    """
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    async_enabled = getattr(request.app.state, "locations_async_enabled", False)
    if not async_enabled:
        job_execution_service = getattr(
            request.app.state, "job_execution_service", None
        )
        trigger_service_sync = getattr(request.app.state, "trigger_service", None)
        job_def_svc = getattr(request.app.state, "job_definition_service", None)
        bootstrap_svc_sync = getattr(request.app.state, "bootstrap_provisioning_service", None)
        if bootstrap_svc_sync is not None:
            try:
                bootstrap_svc_sync.ensure_owner_starter_definitions(user_id)
            except Exception as e:
                logger.warning(
                    "locations_bootstrap_ensure_owner_failed | user_id={} error={}",
                    user_id,
                    e,
                )
        link_repo_sync = getattr(request.app.state, "trigger_job_link_repository", None)
        if job_execution_service and trigger_service_sync and job_def_svc and link_repo_sync:
            normalized_path = _normalize_trigger_path(path)
            trigger = trigger_service_sync.resolve_by_path(normalized_path, user_id)
            if trigger:
                _validate_trigger_secret(authorization, trigger.secret_value)
                linked_ids, dispatchable_ids = _linked_and_dispatchable_job_ids(
                    link_repo_sync, trigger.id, user_id
                )
                _ensure_trigger_has_dispatchable_jobs(linked_ids, dispatchable_ids)
                snapshot = job_def_svc.resolve_for_run(dispatchable_ids[0], user_id, trigger.id)
                if snapshot:
                    run_id = str(uuid.uuid4())
                    trigger_payload = _validate_and_build_trigger_payload(trigger, body)
                    result = job_execution_service.execute_snapshot_run(
                        snapshot=snapshot.snapshot,
                        run_id=run_id,
                        job_id=f"sync_{run_id[:8]}",
                        trigger_payload=trigger_payload,
                        definition_snapshot_ref=snapshot.snapshot_ref,
                        owner_user_id=user_id,
                    )
                    return result
        places_service = getattr(request.app.state, "places_service", None)
        if places_service:
            _validate_legacy_secret(authorization)
            kw = _legacy_keywords_from_body(body)
            if len(kw) > KEYWORDS_MAX_LENGTH:
                raise HTTPException(
                    status_code=400,
                    detail=f"keywords must be at most {KEYWORDS_MAX_LENGTH} characters",
                )
            return places_service.create_place_from_query(kw)
        raise HTTPException(
            status_code=503,
            detail="Unable to run pipeline (sync mode)",
        )

    # Async path: enqueue for worker (fan-out across all linked jobs)
    queue_repo = getattr(request.app.state, "supabase_queue_repository", None)
    run_repo = getattr(request.app.state, "supabase_run_repository", None)
    job_definition_service = getattr(
        request.app.state, "job_definition_service", None
    )
    trigger_service = getattr(request.app.state, "trigger_service", None)
    link_repo = getattr(request.app.state, "trigger_job_link_repository", None)
    if queue_repo is None or run_repo is None:
        logger.warning("locations_enqueue_skipped | supabase_repos_unavailable")
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )
    if job_definition_service is None:
        logger.warning(
            "locations_enqueue_skipped | job_definition_service_unavailable"
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )
    if trigger_service is None:
        logger.warning("locations_enqueue_skipped | trigger_service_unavailable")
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )
    if link_repo is None:
        logger.warning("locations_enqueue_skipped | trigger_job_link_repository_unavailable")
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )

    app_config_repo = getattr(request.app.state, "app_config_repository", None)
    if app_config_repo is None:
        logger.warning("locations_enqueue_skipped | app_config_repository_unavailable")
        raise HTTPException(
            status_code=503,
            detail="Unable to enqueue request",
        )
    eff_limits = app_config_repo.get_by_owner(user_id)
    if eff_limits is None:
        logger.error("locations_enqueue_skipped | effective_limits_unavailable user_id={}", user_id)
        raise HTTPException(
            status_code=503,
            detail="Limits not configured",
        )

    bootstrap_svc = getattr(request.app.state, "bootstrap_provisioning_service", None)
    if bootstrap_svc is not None:
        try:
            bootstrap_svc.ensure_owner_starter_definitions(user_id)
        except Exception as e:
            logger.warning(
                "locations_bootstrap_ensure_owner_failed | user_id={} error={}",
                user_id,
                e,
            )

    normalized_path = _normalize_trigger_path(path)
    trigger = trigger_service.resolve_by_path(normalized_path, user_id)
    if trigger is None:
        logger.error(
            "trigger_enqueue_skipped | trigger_unavailable path={} user_id={}",
            normalized_path,
            user_id,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Trigger not found for path '{normalized_path}' and user",
        )
    _validate_trigger_secret(authorization, trigger.secret_value)
    linked_ids, dispatchable_ids = _linked_and_dispatchable_job_ids(link_repo, trigger.id, user_id)
    _ensure_trigger_has_dispatchable_jobs(linked_ids, dispatchable_ids)

    trigger_payload = _validate_and_build_trigger_payload(trigger, body)
    log_preview = preview_string_for_log(trigger_payload)

    job_ids_accepted: list[str] = []
    run_ids_accepted: list[str] = []
    recipient_whatsapp = None

    for job_definition_id in dispatchable_ids:
        snapshot = job_definition_service.resolve_for_run(
            job_definition_id, user_id, trigger.id
        )
        if snapshot is None:
            logger.warning(
                "locations_enqueue_skipped_job | job_id={} owner={}",
                job_definition_id,
                user_id,
            )
            continue

        job_id = _job_id()
        run_id = str(uuid.uuid4())
        target_data = snapshot.snapshot.get("target") or {}
        target_id = target_data.get("id", "")

        try:
            run_repo.enqueue_production_job_run_with_quota(
                job_id,
                run_id=run_id,
                owner_user_id=user_id,
                trigger_payload=trigger_payload,
                job_definition_id=job_definition_id,
                trigger_id=trigger.id,
                target_id=target_id,
                definition_snapshot_ref=snapshot.snapshot_ref,
                day_cap=eff_limits.max_runs_per_utc_day,
                month_cap=eff_limits.max_runs_per_utc_month,
            )
            payload = {
                "job_id": job_id,
                "run_id": run_id,
                "trigger_payload": trigger_payload,
                "job_definition_id": job_definition_id,
                "trigger_id": trigger.id,
                "job_slug": "notion_place_inserter",
                "definition_snapshot_ref": snapshot.snapshot_ref,
                "owner_user_id": user_id,
            }
            if log_preview:
                payload["keywords"] = log_preview
            if recipient_whatsapp is not None:
                payload["recipient_whatsapp"] = recipient_whatsapp
            send_result = queue_repo.send(payload, delay_seconds=0)
            job_ids_accepted.append(job_id)
            run_ids_accepted.append(run_id)
            logger.debug(
                "locations_enqueue_payload_json | job_id={} run_id={} payload_json={}",
                job_id,
                run_id,
                debug_payload_json_for_logging(payload),
            )
            logger.info(
                "locations_enqueued | job_id={} run_id={} job_definition_id={} definition_snapshot_ref={} "
                "keywords_preview={} pgmq_message_id={} queue_name={}",
                job_id,
                run_id,
                job_definition_id,
                snapshot.snapshot_ref,
                log_preview,
                send_result.message_id,
                queue_repo._config.queue_name,
            )
        except RunQuotaExceeded as e:
            raise HTTPException(status_code=429, detail=e.detail)
        except Exception:
            logger.exception(
                "locations_enqueue_failed | job_id={} run_id={}",
                job_id,
                run_id,
            )
            raise HTTPException(
                status_code=503,
                detail="Unable to enqueue request",
            )

    if not job_ids_accepted:
        raise HTTPException(
            status_code=503,
            detail="Bootstrap job definition unavailable",
        )

    return {"status": "accepted", "job_ids": job_ids_accepted, "run_ids": run_ids_accepted}
