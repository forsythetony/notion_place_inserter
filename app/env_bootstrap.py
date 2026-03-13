"""Environment bootstrap: load .env files at startup with safe precedence."""

from pathlib import Path

from dotenv import load_dotenv

# Env file search order: repo root .env, Render secret file, local convention
DEFAULT_ENV_PATHS = (
    Path(__file__).resolve().parent.parent / ".env",
    Path("/etc/secrets/.env"),
    Path(__file__).resolve().parent.parent / "envs" / "local.env",
)


def load_env_file(paths: tuple[Path, ...] | None = None) -> Path | None:
    """Load first existing .env file; process env vars override file values."""
    search_paths = paths if paths is not None else DEFAULT_ENV_PATHS
    for path in search_paths:
        if path.is_file():
            load_dotenv(path, override=False)
            return path
    return None


def bootstrap_env(paths: tuple[Path, ...] | None = None) -> None:
    """Load env file at startup; process env vars override file values."""
    load_env_file(paths)
