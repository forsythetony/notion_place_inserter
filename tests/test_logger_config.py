"""Tests for loguru dual-sink configuration (console + auto-rotated file)."""

from unittest.mock import patch

import pytest

from app.main import _configure_logger


@pytest.fixture(autouse=True)
def isolate_logger():
    """Restore default logger state after each test."""
    from loguru import logger

    # Remove all handlers added by tests or _configure_logger
    logger.remove()
    # Re-add default stderr so other tests aren't broken
    logger.add(
        lambda msg: None,
        format="{message}",
        level="DEBUG",
    )
    yield
    logger.remove()
    logger.add(lambda msg: None, format="{message}", level="DEBUG")


def test_configure_logger_adds_dual_sinks_and_writes_to_file(tmp_path, monkeypatch):
    """_configure_logger adds stderr and file sinks; file sink writes logs."""
    log_file = tmp_path / "app.log"
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))
    monkeypatch.setenv("LOG_FILE_ROTATION", "10 MB")
    monkeypatch.setenv("LOG_FILE_RETENTION", "3")

    from loguru import logger

    logger.remove()
    _configure_logger()

    logger.info("test_dual_sink_message")

    assert log_file.exists()
    assert "test_dual_sink_message" in log_file.read_text()


def test_configure_logger_honors_env_path_rotation_retention(tmp_path, monkeypatch):
    """_configure_logger passes LOG_FILE_PATH, LOG_FILE_ROTATION, LOG_FILE_RETENTION to file sink."""
    custom_log = tmp_path / "custom" / "logs" / "app.log"
    monkeypatch.setenv("LOG_FILE_PATH", str(custom_log))
    monkeypatch.setenv("LOG_FILE_ROTATION", "50 MB")
    monkeypatch.setenv("LOG_FILE_RETENTION", "5")

    add_calls = []

    def capture_add(*args, **kwargs):
        add_calls.append({"args": args, "kwargs": kwargs})
        return 999  # fake handler id

    from loguru import logger

    with patch.object(logger, "add", side_effect=capture_add):
        logger.remove()
        _configure_logger()

    assert len(add_calls) == 2
    stderr_call = add_calls[0]
    file_call = add_calls[1]

    assert stderr_call["args"][0] is __import__("sys").stderr
    assert file_call["args"][0] == str(custom_log)
    assert file_call["kwargs"]["rotation"] == "50 MB"
    assert file_call["kwargs"]["retention"] == 5


def test_configure_logger_uses_defaults_when_env_unset(monkeypatch):
    """_configure_logger uses default path, rotation, retention when env vars are absent."""
    monkeypatch.delenv("LOG_FILE_PATH", raising=False)
    monkeypatch.delenv("LOG_FILE_ROTATION", raising=False)
    monkeypatch.delenv("LOG_FILE_RETENTION", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    add_calls = []

    def capture_add(*args, **kwargs):
        add_calls.append({"args": args, "kwargs": kwargs})
        return 999

    from loguru import logger

    with patch.object(logger, "add", side_effect=capture_add):
        logger.remove()
        _configure_logger()

    stderr_call = add_calls[0]
    file_call = add_calls[1]
    assert stderr_call["kwargs"]["level"] == "INFO"
    assert file_call["kwargs"]["level"] == "INFO"
    assert file_call["args"][0] == "logs/app.log"
    assert file_call["kwargs"]["rotation"] == "10 MB"
    assert file_call["kwargs"]["retention"] == 3


def test_configure_logger_honors_log_level(monkeypatch):
    """_configure_logger passes LOG_LEVEL to both stderr and file sinks."""
    monkeypatch.delenv("LOG_FILE_PATH", raising=False)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    add_calls = []

    def capture_add(*args, **kwargs):
        add_calls.append({"args": args, "kwargs": kwargs})
        return 999

    from loguru import logger

    with patch.object(logger, "add", side_effect=capture_add):
        logger.remove()
        _configure_logger()

    assert add_calls[0]["kwargs"]["level"] == "DEBUG"
    assert add_calls[1]["kwargs"]["level"] == "DEBUG"


def test_configure_logger_creates_parent_directory(tmp_path, monkeypatch):
    """_configure_logger creates parent directory for log file when it does not exist."""
    nested = tmp_path / "nested" / "dir" / "app.log"
    monkeypatch.setenv("LOG_FILE_PATH", str(nested))

    from loguru import logger

    logger.remove()
    _configure_logger()

    assert nested.parent.exists()
    assert nested.parent.is_dir()


def test_configure_logger_handles_braces_in_message_and_context(tmp_path, monkeypatch):
    """Logger format escapes braces in message/extra content without crashing."""
    log_file = tmp_path / "app.log"
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    from loguru import logger

    logger.remove()
    _configure_logger()

    logger.bind(candidate_context={"primaryType": "restaurant"}).info(
        "brace_payload | raw={}",
        '{"a": 1, "b": {"c": 2}}',
    )

    text = log_file.read_text()
    assert "brace_payload" in text
    assert "candidate_context={'primaryType': 'restaurant'}" in text
