"""Upload Image to Notion step runtime handler."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response

# Max size for external image fetch (5MB)
_MAX_FETCH_BYTES = 5 * 1024 * 1024
_DEFAULT_TIMEOUT_MS = 15000


def _fetch_image_bytes(url: str, timeout_seconds: float) -> bytes | None:
    """Fetch image bytes from URL. Returns None on failure."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return None
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.content
            if len(data) > _MAX_FETCH_BYTES:
                logger.warning(
                    "upload_image_fetch_too_large | url_len={} bytes={} max={}",
                    len(url),
                    len(data),
                    _MAX_FETCH_BYTES,
                )
                return None
            return data
    except Exception as exc:
        logger.warning(
            "upload_image_fetch_failed | url_len={} error={}",
            len(url),
            str(exc),
        )
        return None


def _is_google_photo_name(value: str) -> bool:
    """Check if value looks like a Google Places photo resource name."""
    if not value or not isinstance(value, str):
        return False
    return value.strip().startswith("places/") and "/photos/" in value


class UploadImageToNotionHandler(StepRuntime):
    """Fetch image (URL or Google photo name) and upload to Notion; return payload for icon/cover."""

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        input_bindings: dict[str, Any],
        resolved_inputs: dict[str, Any],
        ctx: ExecutionContext,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        value = resolved_inputs.get("value")
        if value is None:
            return {"notion_image_url": None}

        if isinstance(value, dict):
            # Already a Notion payload (e.g. from dry-run passthrough)
            if value.get("type") in ("external", "file", "file_upload"):
                return {"notion_image_url": value}
            # Extract URL from external payload
            ext = value.get("external") or {}
            if isinstance(ext, dict) and ext.get("url"):
                value = ext["url"]
            else:
                return {"notion_image_url": None}

        url_or_name = str(value).strip() if value else ""
        if not url_or_name:
            return {"notion_image_url": None}

        manual = consume_manual_api_response(ctx, "notion.upload_image")
        if manual is not None:
            ctx.log_step_processing("Using live-test manual API override (notion.upload_image).")
            if isinstance(manual, dict):
                return {"notion_image_url": manual.get("notion_image_url")}
            return {"notion_image_url": None}

        notion = ctx.get_service("notion")
        google = ctx.get_service("google_places")
        token_getter = ctx.get_service("get_notion_token")
        dry_run = getattr(ctx, "dry_run", False)
        allow_writes = getattr(ctx, "allow_destination_writes", True)

        if not allow_writes:
            ctx.log_step_processing(
                "Live test: destination writes disabled; using external image URL only if possible."
            )
            logger.info(
                "upload_image_to_notion_skipped | step_id={} reason=no_destination_writes use_external_only",
                step_id,
            )
            if _is_google_photo_name(url_or_name):
                if google:
                    ext_url = google.get_photo_url(url_or_name)
                    if ext_url:
                        return {
                            "notion_image_url": {"type": "external", "external": {"url": ext_url}}
                        }
                return {"notion_image_url": None}
            if url_or_name.startswith(("http://", "https://")):
                return {
                    "notion_image_url": {"type": "external", "external": {"url": url_or_name}}
                }
            return {"notion_image_url": None}

        if dry_run:
            ctx.log_step_processing("Dry run: skipping Notion file upload; returning external URL payload if possible.")
            # Never upload during dry-run mode. Prefer external URL payloads.
            if _is_google_photo_name(url_or_name):
                if google:
                    ext_url = google.get_photo_url(url_or_name)
                    if ext_url:
                        return {
                            "notion_image_url": {"type": "external", "external": {"url": ext_url}}
                        }
                return {"notion_image_url": None}
            if url_or_name.startswith(("http://", "https://")):
                return {
                    "notion_image_url": {"type": "external", "external": {"url": url_or_name}}
                }
            return {"notion_image_url": None}

        image_bytes: bytes | None = None
        if _is_google_photo_name(url_or_name):
            ctx.log_step_processing("Fetching image bytes from Google Places photo resource.")
            if google:
                image_bytes = google.get_photo_bytes(url_or_name)
        else:
            ctx.log_step_processing("Fetching image bytes from HTTP URL.")
            timeout_ms = config.get("timeout_ms") or _DEFAULT_TIMEOUT_MS
            timeout_seconds = max(1.0, min(60.0, timeout_ms / 1000.0))
            image_bytes = _fetch_image_bytes(url_or_name, timeout_seconds)

        if not image_bytes or not notion:
            ctx.log_step_processing("No image bytes or Notion client; cannot upload.")
            return {"notion_image_url": None}

        ctx.log_step_processing("Uploading image bytes to Notion (file upload).")
        upload_kwargs: dict[str, Any] = {
            "filename": "image.jpg",
            "content_type": "image/jpeg",
        }
        owner_user_id = getattr(ctx, "owner_user_id", "") or ""
        access_token: str | None = None
        if callable(token_getter) and owner_user_id:
            access_token = token_getter(owner_user_id)
            if access_token:
                # Keep upload + page creation on the same Notion credential context.
                upload_kwargs["access_token"] = access_token
                logger.debug(
                    "notion_upload_token_source | run_id={} step_id={} owner_user_id={} token_source=oauth",
                    getattr(ctx, "run_id", ""),
                    step_id,
                    owner_user_id,
                )
            else:
                # TODO: Remove global token fallback in future PR. Require OAuth for all Notion uploads.
                logger.warning(
                    "notion_upload_fallback_to_global_token | run_id={} step_id={} owner_user_id={} "
                    "reason=oauth_token_unavailable",
                    getattr(ctx, "run_id", ""),
                    step_id,
                    owner_user_id,
                )
        elif owner_user_id and not callable(token_getter):
            logger.warning(
                "notion_upload_fallback_to_global_token | run_id={} step_id={} owner_user_id={} "
                "reason=token_getter_unavailable",
                getattr(ctx, "run_id", ""),
                step_id,
                owner_user_id,
            )

        payload = notion.upload_cover_from_bytes(image_bytes, **upload_kwargs)
        return {"notion_image_url": payload}
