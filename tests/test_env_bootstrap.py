"""Tests for env file loading."""

import os
from pathlib import Path

import pytest

from app.env_bootstrap import DEFAULT_ENV_PATHS, load_env_file


def test_load_env_file_loads_first_existing(tmp_path):
    """First existing file in search order is loaded."""
    env1 = tmp_path / "first.env"
    env1.write_text("ENV_BOOTSTRAP_TEST=from_first\n")
    env2 = tmp_path / "second.env"
    env2.write_text("ENV_BOOTSTRAP_TEST=from_second\n")

    paths = (env1, env2)
    result = load_env_file(paths)
    assert result == env1
    assert os.environ.get("ENV_BOOTSTRAP_TEST") == "from_first"

    # Cleanup
    del os.environ["ENV_BOOTSTRAP_TEST"]


def test_load_env_file_skips_missing_uses_second(tmp_path):
    """Missing first path is skipped; second existing file is loaded."""
    env2 = tmp_path / "second.env"
    env2.write_text("ENV_BOOTSTRAP_TEST=from_second\n")

    paths = (tmp_path / "nonexistent.env", env2)
    result = load_env_file(paths)
    assert result == env2
    assert os.environ.get("ENV_BOOTSTRAP_TEST") == "from_second"

    del os.environ["ENV_BOOTSTRAP_TEST"]


def test_load_env_file_override_false_preserves_existing(tmp_path):
    """Process env vars are not overwritten by file (override=False)."""
    env_file = tmp_path / "env.env"
    env_file.write_text("ENV_BOOTSTRAP_OVERRIDE=from_file\n")

    os.environ["ENV_BOOTSTRAP_OVERRIDE"] = "from_process"
    load_env_file((env_file,))
    assert os.environ.get("ENV_BOOTSTRAP_OVERRIDE") == "from_process"

    del os.environ["ENV_BOOTSTRAP_OVERRIDE"]


def test_load_env_file_returns_none_when_no_file_exists(tmp_path):
    """Returns None when no path exists."""
    paths = (tmp_path / "a.env", tmp_path / "b.env")
    result = load_env_file(paths)
    assert result is None


def test_load_env_file_loads_SECRET_uppercase(tmp_path):
    """SECRET from .env is loaded and available as uppercase (no remapping)."""
    env_file = tmp_path / "env.env"
    env_file.write_text("SECRET=my-auth-secret\n")

    orig = os.environ.pop("SECRET", None)
    try:
        load_env_file((env_file,))
        assert os.environ.get("SECRET") == "my-auth-secret"
    finally:
        if orig is not None:
            os.environ["SECRET"] = orig
        elif "SECRET" in os.environ:
            del os.environ["SECRET"]


def test_default_env_paths_has_expected_order():
    """DEFAULT_ENV_PATHS lists .env, /etc/secrets/.env, envs/local.env in order."""
    assert len(DEFAULT_ENV_PATHS) == 3
    assert DEFAULT_ENV_PATHS[0].name == ".env"
    assert str(DEFAULT_ENV_PATHS[1]) == "/etc/secrets/.env"
    assert DEFAULT_ENV_PATHS[2].name == "local.env"
    assert "envs" in str(DEFAULT_ENV_PATHS[2])
