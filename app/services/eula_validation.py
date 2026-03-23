"""EULA plain-language summary schema and content hash (UTF-8 SHA-256 hex)."""

from __future__ import annotations

import hashlib
from typing import Any

_ALLOWED_SUMMARY_KEYS = frozenset({"dos", "donts", "cautions"})


def compute_content_sha256(full_text: str) -> str:
    """Hex-encoded SHA-256 of full_text encoded as UTF-8."""
    return hashlib.sha256(full_text.encode("utf-8")).hexdigest()


def validate_plain_language_summary(obj: Any) -> dict[str, list[str]]:
    """
    Strict schema: only keys dos, donts, cautions — each a list of non-empty strings.
    Raises ValueError with a deterministic message on invalid input.
    """
    if not isinstance(obj, dict):
        raise ValueError("plain_language_summary must be a JSON object")

    keys = set(obj.keys())
    if keys != _ALLOWED_SUMMARY_KEYS:
        extra = keys - _ALLOWED_SUMMARY_KEYS
        missing = _ALLOWED_SUMMARY_KEYS - keys
        parts: list[str] = []
        if extra:
            parts.append(f"unknown keys: {sorted(extra)}")
        if missing:
            parts.append(f"missing keys: {sorted(missing)}")
        raise ValueError("plain_language_summary " + "; ".join(parts))

    out: dict[str, list[str]] = {}
    for k in ("dos", "donts", "cautions"):
        v = obj[k]
        if not isinstance(v, list):
            raise ValueError(f"plain_language_summary.{k} must be an array")
        items: list[str] = []
        for i, item in enumerate(v):
            if not isinstance(item, str):
                raise ValueError(
                    f"plain_language_summary.{k}[{i}] must be a string"
                )
            s = item.strip()
            if not s:
                raise ValueError(
                    f"plain_language_summary.{k}[{i}] must be non-empty"
                )
            items.append(s)
        out[k] = items
    return out
