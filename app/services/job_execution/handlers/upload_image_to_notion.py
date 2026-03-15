"""Upload Image to Notion step runtime handler."""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from app.services.job_execution.runtime_types import ExecutionContext
from app.services.job_execution.step_runtime_base import StepRuntime

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

        notion = ctx.get_service("notion")
        google = ctx.get_service("google_places")
        dry_run = getattr(ctx, "dry_run", False)

        image_bytes: bytes | None = None

        if _is_google_photo_name(url_or_name):
            if google:
                image_bytes = google.get_photo_bytes(url_or_name)
            if not image_bytes and google and dry_run:
                ext_url = google.get_photo_url(url_or_name)
                if ext_url:
                    return {
                        "notion_image_url": {"type": "external", "external": {"url": ext_url}}
                    }
        else:
            timeout_ms = config.get("timeout_ms") or _DEFAULT_TIMEOUT_MS
            timeout_seconds = max(1.0, min(60.0, timeout_ms / 1000.0))
            image_bytes = _fetch_image_bytes(url_or_name, timeout_seconds)
            if not image_bytes and dry_run and url_or_name.startswith(("http://", "https://")):
                return {
                    "notion_image_url": {"type": "external", "external": {"url": url_or_name}}
                }

        if not image_bytes or not notion:
            return {"notion_image_url": None}

        payload = notion.upload_cover_from_bytes(
            image_bytes,
            filename="image.jpg",
            content_type="image/jpeg",
        )
        return {"notion_image_url": payload}
