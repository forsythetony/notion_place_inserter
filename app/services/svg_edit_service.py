"""Fetch SVG from URL, apply tint, upload to R2 (icons/beta)."""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

import httpx
from loguru import logger

from app.services.job_execution.runtime_types import StepExecutionHandle
from app.services.r2_media_storage_service import R2MediaStorageService

# Align with upload_image_to_notion fetch cap
_MAX_FETCH_BYTES = 5 * 1024 * 1024
_DEFAULT_TIMEOUT_MS = 15000

_BETA_PREFIX = "icons/beta"


def normalize_hex_color(raw: str | None) -> str | None:
    """Return #rrggbb or None if invalid."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3 and all(c in "0123456789abcdefABCDEF" for c in s):
        return "#" + "".join(c * 2 for c in s).lower()
    if len(s) == 6 and all(c in "0123456789abcdefABCDEF" for c in s):
        return "#" + s.lower()
    return None


def _should_skip_paint_value(val: str) -> bool:
    low = val.strip().lower()
    return low in ("none", "transparent") or low.startswith("url(")


def tint_svg_markup(svg_text: str, tint_hex: str) -> str:
    """
    Apply a solid tint to SVG markup: replace solid fill/stroke colors and currentColor.
    Skips none, transparent, and url(...) references.
    """
    t = tint_hex if tint_hex.startswith("#") else f"#{tint_hex}"
    t = normalize_hex_color(t) or t

    def sub_attr(name: str, m: re.Match[str]) -> str:
        val = m.group(1)
        if _should_skip_paint_value(val):
            return m.group(0)
        return f'{name}="{t}"'

    def sub_attr_squote(name: str, m: re.Match[str]) -> str:
        val = m.group(1)
        if _should_skip_paint_value(val):
            return m.group(0)
        return f"{name}='{t}'"

    out = svg_text
    out = re.sub(r'fill="([^"]*)"', lambda m: sub_attr("fill", m), out, flags=re.IGNORECASE)
    out = re.sub(r"fill='([^']*)'", lambda m: sub_attr_squote("fill", m), out, flags=re.IGNORECASE)
    out = re.sub(r'stroke="([^"]*)"', lambda m: sub_attr("stroke", m), out, flags=re.IGNORECASE)
    out = re.sub(r"stroke='([^']*)'", lambda m: sub_attr_squote("stroke", m), out, flags=re.IGNORECASE)

    out = re.sub(r'fill\s*=\s*"currentColor"', f'fill="{t}"', out, flags=re.IGNORECASE)
    out = re.sub(r"fill\s*=\s*'currentColor'", f"fill='{t}'", out, flags=re.IGNORECASE)
    out = re.sub(r'stroke\s*=\s*"currentColor"', f'stroke="{t}"', out, flags=re.IGNORECASE)
    out = re.sub(r"stroke\s*=\s*'currentColor'", f"stroke='{t}'", out, flags=re.IGNORECASE)

    def patch_style(m: re.Match[str]) -> str:
        block = m.group(1)

        def rep_fill(mm: re.Match[str]) -> str:
            if _should_skip_paint_value(mm.group(1)):
                return mm.group(0)
            return f"fill:{t}"

        def rep_stroke(mm: re.Match[str]) -> str:
            if _should_skip_paint_value(mm.group(1)):
                return mm.group(0)
            return f"stroke:{t}"

        block = re.sub(r"fill\s*:\s*([^;]+)", rep_fill, block, flags=re.IGNORECASE)
        block = re.sub(r"stroke\s*:\s*([^;]+)", rep_stroke, block, flags=re.IGNORECASE)
        return f'style="{block}"'

    out = re.sub(r'style="([^"]*)"', patch_style, out, flags=re.IGNORECASE)
    return out


def _is_probably_svg(data: bytes) -> bool:
    head = data[:4000].lower()
    return b"<svg" in head or (data.strip().startswith(b"<") and b"svg" in head[:200])


async def _fetch_svg_bytes(url: str, timeout_seconds: float) -> bytes | None:
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            data = resp.content
            if len(data) > _MAX_FETCH_BYTES:
                logger.warning(
                    "svg_edit_fetch_too_large | url_len={} bytes={} max={}",
                    len(url),
                    len(data),
                    _MAX_FETCH_BYTES,
                )
                return None
            return data
    except Exception as exc:
        logger.warning("svg_edit_fetch_failed | url_len={} error={}", len(url), str(exc))
        return None


class SvgEditService:
    """Tint SVG assets and upload to R2 under icons/beta/."""

    def __init__(self, storage: R2MediaStorageService | None) -> None:
        self._storage = storage

    @property
    def storage(self) -> R2MediaStorageService | None:
        return self._storage

    async def fetch_tint_upload(
        self,
        *,
        source_url: str,
        tint_hex: str,
        step_handle: StepExecutionHandle,
        dry_run: bool = False,
        allow_destination_writes: bool = True,
    ) -> dict[str, Any]:
        """
        Returns dict with keys: ok (bool), image_url (str), error_detail (optional).
        On dry_run or !allow_destination_writes, skips R2 and returns source_url as passthrough when fetch succeeds.
        """
        step_handle.log_processing(
            f"[SvgEditService] Starting fetch_tint_upload source_url_len={len(source_url)} "
            f"tint={tint_hex!r}"
        )
        norm = normalize_hex_color(tint_hex)
        if not norm:
            step_handle.log_processing("[SvgEditService] Invalid tint_color; expected #RGB or #RRGGBB.")
            return {
                "ok": False,
                "image_url": "",
                "error_detail": {"reason": "invalid_tint_color"},
            }

        timeout_ms = _DEFAULT_TIMEOUT_MS
        timeout_seconds = max(1.0, min(60.0, timeout_ms / 1000.0))
        raw = await _fetch_svg_bytes(source_url, timeout_seconds)
        if not raw:
            step_handle.log_processing("[SvgEditService] Fetch failed or empty body.")
            return {
                "ok": False,
                "image_url": "",
                "error_detail": {"reason": "fetch_failed"},
            }

        if not _is_probably_svg(raw):
            step_handle.log_processing("[SvgEditService] Response does not look like SVG; refusing to process.")
            return {
                "ok": False,
                "image_url": "",
                "error_detail": {"reason": "not_svg"},
            }

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")

        tinted = tint_svg_markup(text, norm)
        body = tinted.encode("utf-8")

        if dry_run or not allow_destination_writes:
            step_handle.log_processing(
                "[SvgEditService] Skipping R2 upload (dry_run or destination writes disabled); "
                "returning original source URL."
            )
            return {
                "ok": True,
                "image_url": source_url.strip(),
                "passthrough": True,
            }

        if self._storage is None:
            step_handle.log_processing("[SvgEditService] R2 storage not configured; cannot upload.")
            return {
                "ok": False,
                "image_url": "",
                "error_detail": {"reason": "r2_unavailable"},
            }

        object_id = str(uuid.uuid4())
        rel_key = f"{_BETA_PREFIX}/{object_id}.svg"
        storage_key = self._storage.prefixed_object_key(rel_key)
        step_handle.log_processing(
            f"[SvgEditService] Uploading tinted SVG to R2 key={storage_key!r} bytes={len(body)}"
        )

        def _put() -> None:
            self._storage.put_object(
                key=storage_key,
                body=body,
                content_type="image/svg+xml",
            )

        await asyncio.to_thread(_put)
        public_url = self._storage.public_url_for_key(storage_key)
        step_handle.log_processing(f"[SvgEditService] Upload complete public_url_len={len(public_url)}")
        return {"ok": True, "image_url": public_url}
