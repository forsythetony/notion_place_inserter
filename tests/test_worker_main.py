"""Tests for worker entrypoint lifecycle and shutdown cleanup."""

from unittest.mock import MagicMock

import pytest

from app.worker_main import _cleanup_queue_repo


def test_cleanup_queue_repo_invokes_close():
    """_cleanup_queue_repo calls close() when repo has callable close."""
    mock_repo = MagicMock()
    _cleanup_queue_repo(mock_repo)
    mock_repo.close.assert_called_once()


def test_cleanup_queue_repo_no_close_does_not_raise():
    """_cleanup_queue_repo does not raise when repo has no close method."""
    mock_repo = MagicMock(spec=[])  # no close attribute
    _cleanup_queue_repo(mock_repo)  # no raise


def test_cleanup_queue_repo_close_error_logged_does_not_raise():
    """_cleanup_queue_repo logs but does not raise when close() raises."""
    mock_repo = MagicMock()
    mock_repo.close.side_effect = RuntimeError("connection reset")
    _cleanup_queue_repo(mock_repo)  # no raise
