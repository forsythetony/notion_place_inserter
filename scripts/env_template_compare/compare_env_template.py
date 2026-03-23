#!/usr/bin/env python3
"""Compare envs/env.template keys/values against envs/local.env or envs/prod.env."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.table import Table

# Mirror app/env_bootstrap.py — keep this tool import-free from the app package.
SENSITIVE_ENV_KEYS: frozenset[str] = frozenset(
    {
        "SECRET",
        "SUPABASE_SECRET_KEY",
        "NOTION_API_KEY",
        "NOTION_OAUTH_CLIENT_SECRET",
        "ANTHROPIC_TOKEN",
        "GOOGLE_PLACES_API_KEY",
        "FREEPIK_API_KEY",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
    }
)

_LINE_ACTIVE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$",
)
_LINE_TEMPLATE = re.compile(
    r"^\s*(?:#\s*)?(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def parse_active_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        logger.error("Env file not found: {}", path)
        sys.exit(1)
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE_ACTIVE.match(raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        out[key] = val.rstrip("\r")
    return out


def parse_template(path: Path) -> tuple[set[str], dict[str, str]]:
    if not path.is_file():
        logger.error("Template not found: {}", path)
        sys.exit(1)
    keys: set[str] = set()
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = _LINE_TEMPLATE.match(raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        keys.add(key)
        values[key] = val.rstrip("\r")
    return keys, values


def mask(key: str, value: str, *, no_mask: bool) -> str:
    if no_mask:
        return value
    if not value:
        return ""
    if key in SENSITIVE_ENV_KEYS:
        return "*" * len(value)
    return value


def pick_target_with_fzf() -> str:
    if not shutil.which("fzf"):
        logger.error("fzf not found in PATH; install fzf or use --target local|prod")
        sys.exit(1)
    # fzf draws its TUI on stderr; capturing stderr (capture_output=True) breaks the UI and can hang.
    proc = subprocess.run(
        ["fzf", "--prompt=Compare template → ", "--height=~12"],
        input="local\nprod\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=None,
    )
    if proc.returncode != 0:
        sys.exit(0)
    choice = (proc.stdout or "").strip()
    if choice not in ("local", "prod"):
        logger.error("Unexpected fzf selection: {!r}", choice)
        sys.exit(1)
    return choice


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare env.template to envs/local.env or envs/prod.env "
            "(pick target with fzf unless --target is set)."
        ),
    )
    parser.add_argument(
        "--target",
        choices=("local", "prod"),
        help="Skip fzf and use this env file (envs/local.env or envs/prod.env).",
    )
    parser.add_argument(
        "--no-mask",
        action="store_true",
        help="Show sensitive values in plain text (avoid in shared screens).",
    )
    args = parser.parse_args()

    root = repo_root()
    template_path = root / "envs" / "env.template"
    template_keys, _ = parse_template(template_path)

    target = args.target or pick_target_with_fzf()
    env_path = root / "envs" / f"{target}.env"
    env_values = parse_active_env(env_path)

    all_keys = sorted(template_keys | set(env_values.keys()))

    table = Table(
        title=f"env.template vs envs/{target}.env",
        show_header=True,
        header_style="bold",
    )
    # Three columns: variable name, template membership, value in selected env (local or prod).
    table.add_column("Variable", style="cyan", no_wrap=True, max_width=36)
    table.add_column("In template?", justify="center", max_width=14)
    table.add_column(
        f"Value ({target})",
        overflow="ellipsis",
        max_width=72,
    )

    for key in all_keys:
        in_tpl = "yes" if key in template_keys else "no"
        env_val = env_values.get(key)
        if env_val is None:
            env_cell = "[dim](unset)[/dim]"
        else:
            env_cell = mask(key, env_val, no_mask=args.no_mask) or "[dim](empty)[/dim]"
        table.add_row(key, in_tpl, env_cell)

    console = Console()
    console.print(table)
    console.print(f"\n[dim]Template: {template_path}[/dim]")
    console.print(f"[dim]Compared: {env_path}[/dim]")


if __name__ == "__main__":
    main()
