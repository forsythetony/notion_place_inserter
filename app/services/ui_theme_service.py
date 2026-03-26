"""UI theme presets: defaults merge, validation, CSS variable mapping."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.repositories.postgres_ui_theme_repository import PostgresUiThemeRepository

# Max stored config JSON size (bytes) — p5_admin-runtime-theme-spec §11
MAX_CONFIG_JSON_BYTES = 256 * 1024

# Default token tree (Calm Graphite — aligned with notion_pipeliner_ui index.css)
DEFAULT_THEME_TOKENS: dict[str, Any] = {
    "color": {
        "primary": "#7AA2F7",
        "secondary": "#A9B3C3",
        "secondaryTint": "#6B7280",
        "surface": "#161A22",
        "text": "#E8EDF5",
    },
    "radius": {
        "buttonPrimary": "8px",
        "buttonSecondary": "6px",
    },
    "typography": {
        "fontFamilySans": "system-ui, Segoe UI, Roboto, sans-serif",
    },
    "graph": {
        "edgeStroke": "#2A3140",
    },
}

_CSS_VAR_PREFIX = "--pipeliner-"


def _segment_to_kebab(segment: str) -> str:
    if "_" in segment:
        return segment.replace("_", "-").lower()
    return re.sub(r"(?<!^)(?=[A-Z])", "-", segment).lower()


def deep_merge_tokens(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    """Deep-merge dicts; override wins on leaf conflicts. Does not mutate inputs."""
    if not override:
        return copy.deepcopy(base)
    out = copy.deepcopy(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = deep_merge_tokens(out[key], val)
        else:
            out[key] = copy.deepcopy(val) if isinstance(val, dict) else val
    return out


def _flatten_tokens_to_css_vars(
    obj: dict[str, Any], path_segments: tuple[str, ...] = ()
) -> dict[str, str]:
    """Flatten nested token dict to --pipeliner-* CSS variable names."""
    out: dict[str, str] = {}
    for key, val in obj.items():
        seg = _segment_to_kebab(str(key))
        next_path = path_segments + (seg,)
        if isinstance(val, dict):
            out.update(_flatten_tokens_to_css_vars(val, next_path))
        else:
            name = _CSS_VAR_PREFIX + "-".join(next_path)
            out[name] = str(val)
    return out


def _collect_leaf_validation_errors(obj: Any, path: str) -> list[str]:
    """Ensure token leaves are strings; nested dicts allowed."""
    errors: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = f"{path}.{k}" if path else str(k)
            errors.extend(_collect_leaf_validation_errors(v, child))
    elif isinstance(obj, list):
        errors.append(f"{path}: arrays are not allowed in tokens")
    elif not isinstance(obj, str):
        errors.append(f"{path}: expected string, got {type(obj).__name__}")
    return errors


class UiThemeStoredConfig(BaseModel):
    """Stored JSON shape in ui_theme_presets.config."""

    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(alias="schemaVersion", ge=1)
    tokens: dict[str, Any] = Field(default_factory=dict)


def validate_config_json_size(raw: bytes | str) -> list[str]:
    if isinstance(raw, str):
        raw_b = raw.encode("utf-8")
    else:
        raw_b = raw
    if len(raw_b) > MAX_CONFIG_JSON_BYTES:
        return [f"config JSON exceeds maximum size ({MAX_CONFIG_JSON_BYTES} bytes)"]
    return []


def parse_and_validate_stored_config(data: dict[str, Any]) -> tuple[UiThemeStoredConfig | None, list[str]]:
    """Returns (model, errors)."""
    errs = validate_config_json_size(json.dumps(data, separators=(",", ":")))
    if errs:
        return None, errs
    try:
        m = UiThemeStoredConfig.model_validate(data)
    except Exception as e:
        return None, [str(e)]
    terr = _collect_leaf_validation_errors(m.tokens, "tokens")
    if terr:
        return None, terr
    if m.schema_version != 1:
        return None, [f"unsupported schemaVersion {m.schema_version}; only 1 is supported"]
    return m, []


class UiThemeService:
    def __init__(self, repo: PostgresUiThemeRepository) -> None:
        self._repo = repo

    def build_merged_tokens(self, preset_config: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
        """Merge defaults with preset config.tokens. Returns (schema_version, merged_tokens)."""
        if not preset_config:
            return 1, copy.deepcopy(DEFAULT_THEME_TOKENS)
        m, errs = parse_and_validate_stored_config(preset_config)
        if m is None:
            raise ValueError(errs[0] if errs else "invalid config")
        sv = m.schema_version
        merged = deep_merge_tokens(DEFAULT_THEME_TOKENS, m.tokens)
        return sv, merged

    async def get_runtime_payload(self) -> dict[str, Any]:
        active_id = await self._repo.get_active_preset_id()
        if not active_id:
            merged = copy.deepcopy(DEFAULT_THEME_TOKENS)
            css_vars = _flatten_tokens_to_css_vars(merged)
            return {
                "schemaVersion": 1,
                "presetId": None,
                "cssVars": css_vars,
            }
        preset = await self._repo.get_preset_by_id(active_id)
        if not preset:
            merged = copy.deepcopy(DEFAULT_THEME_TOKENS)
            css_vars = _flatten_tokens_to_css_vars(merged)
            return {
                "schemaVersion": 1,
                "presetId": None,
                "cssVars": css_vars,
            }
        cfg = preset.get("config") or {}
        try:
            sv, merged = self.build_merged_tokens(cfg)
        except ValueError:
            merged = copy.deepcopy(DEFAULT_THEME_TOKENS)
            sv = 1
        css_vars = _flatten_tokens_to_css_vars(merged)
        return {
            "schemaVersion": sv,
            "presetId": str(preset["id"]),
            "cssVars": css_vars,
        }

    async def get_active_for_admin(self) -> dict[str, Any]:
        """Runtime resolution plus raw config for editor."""
        runtime = await self.get_runtime_payload()
        active_id = await self._repo.get_active_preset_id()
        raw: dict[str, Any] | None = None
        if active_id:
            p = await self._repo.get_preset_by_id(active_id)
            if p:
                raw = p.get("config")
        return {
            "schemaVersion": runtime["schemaVersion"],
            "presetId": runtime["presetId"],
            "cssVars": runtime["cssVars"],
            "config": raw,
            "activePresetId": active_id,
        }

    def preview_derived_config(
        self,
        base_config: dict[str, Any],
        target: Literal["dark", "light"],
    ) -> dict[str, Any]:
        """
        Deterministic editor-only helper: merge base with a fixed dark or light palette
        for known color roles. Does not auto-apply on GET /theme/runtime.
        """
        m, errs = parse_and_validate_stored_config(base_config)
        if m is None:
            raise ValueError(errs[0] if errs else "invalid config")
        tokens = copy.deepcopy(m.tokens)
        color = tokens.get("color")
        if not isinstance(color, dict):
            color = {}
            tokens["color"] = color
        if target == "dark":
            overlay = {
                "primary": "#7AA2F7",
                "secondary": "#A9B3C3",
                "secondaryTint": "#718096",
                "surface": "#111318",
                "text": "#E8EDF5",
            }
        else:
            overlay = {
                "primary": "#2563EB",
                "secondary": "#4B5563",
                "secondaryTint": "#9CA3AF",
                "surface": "#F7FAFC",
                "text": "#1A202C",
            }
        for k, v in overlay.items():
            color[k] = v
        return {"schemaVersion": 1, "tokens": tokens}
