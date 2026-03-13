"""Unit tests for Supabase config parsing and validation."""

import os
from unittest.mock import patch

import pytest

from app.integrations.supabase_config import SupabaseConfig, load_supabase_config


def test_load_supabase_config_success():
    """With valid env vars, config loads with expected values."""
    with patch.dict(
        os.environ,
        {
            "SUPABASE_URL": "https://abc.supabase.co",
            "SUPABASE_SECRET_KEY": "secret-key-123",
        },
        clear=False,
    ):
        cfg = load_supabase_config()
    assert cfg.url == "https://abc.supabase.co"
    assert cfg.secret_key == "secret-key-123"
    assert cfg.queue_name == "locations_jobs"
    assert cfg.table_platform_jobs == "platform_jobs"
    assert cfg.table_pipeline_runs == "pipeline_runs"
    assert cfg.table_pipeline_run_events == "pipeline_run_events"


def test_load_supabase_config_with_overrides():
    """Optional env overrides are applied."""
    with patch.dict(
        os.environ,
        {
            "SUPABASE_URL": "https://xyz.supabase.co",
            "SUPABASE_SECRET_KEY": "key",
            "SUPABASE_QUEUE_NAME": "custom_queue",
            "SUPABASE_TABLE_PLATFORM_JOBS": "jobs",
        },
        clear=False,
    ):
        cfg = load_supabase_config()
    assert cfg.queue_name == "custom_queue"
    assert cfg.table_platform_jobs == "jobs"
    assert cfg.table_pipeline_runs == "pipeline_runs"


def test_load_supabase_config_missing_url():
    """Missing/empty SUPABASE_URL raises with clear error."""
    with patch.dict(
        os.environ,
        {"SUPABASE_URL": "", "SUPABASE_SECRET_KEY": "key"},
        clear=False,
    ):
        with pytest.raises(RuntimeError) as exc_info:
            load_supabase_config()
    assert "SUPABASE_URL" in str(exc_info.value)
    assert "required" in str(exc_info.value).lower()


def test_load_supabase_config_missing_secret_key():
    """Missing/empty SUPABASE_SECRET_KEY raises with clear error."""
    with patch.dict(
        os.environ,
        {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SECRET_KEY": ""},
        clear=False,
    ):
        with pytest.raises(RuntimeError) as exc_info:
            load_supabase_config()
    assert "SUPABASE_SECRET_KEY" in str(exc_info.value)
    assert "required" in str(exc_info.value).lower()


def test_load_supabase_config_empty_url():
    """Empty SUPABASE_URL raises."""
    with patch.dict(
        os.environ,
        {"SUPABASE_URL": "  ", "SUPABASE_SECRET_KEY": "key"},
        clear=False,
    ):
        with pytest.raises(RuntimeError) as exc_info:
            load_supabase_config()
    assert "SUPABASE_URL" in str(exc_info.value)


def test_load_supabase_config_malformed_url():
    """Non-https URL to non-local host raises with actionable message."""
    with patch.dict(
        os.environ,
        {
            "SUPABASE_URL": "http://insecure.supabase.co",
            "SUPABASE_SECRET_KEY": "key",
        },
        clear=False,
    ):
        with pytest.raises(RuntimeError) as exc_info:
            load_supabase_config()
    assert "https" in str(exc_info.value).lower()
    assert "SUPABASE_URL" in str(exc_info.value)


def test_load_supabase_config_local_url():
    """Local Supabase http://127.0.0.1 or localhost is accepted."""
    for url in ("http://127.0.0.1:54321", "http://localhost:54321"):
        with patch.dict(
            os.environ,
            {"SUPABASE_URL": url, "SUPABASE_SECRET_KEY": "key"},
            clear=False,
        ):
            cfg = load_supabase_config()
        assert cfg.url == url
