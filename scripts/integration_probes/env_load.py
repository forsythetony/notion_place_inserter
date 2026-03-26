"""Shared env loading for integration probe scripts."""

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_probe_env(path: str | Path) -> Path:
    """
    Load env vars from a file. ``override=True`` so the file wins over any
    values already in the process environment for this diagnostic run.
    """
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.is_file():
        raise FileNotFoundError(f"Env file not found: {p}")
    load_dotenv(p, override=True)
    return p
