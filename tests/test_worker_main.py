"""Tests for worker entrypoint lifecycle and shutdown cleanup."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.worker_main import _aclose_queue_repo_best_effort


def test_aclose_queue_repo_invokes_aclose():
    """_aclose_queue_repo_best_effort awaits aclose() when repo has callable aclose."""
    mock_repo = MagicMock()
    mock_repo.aclose = AsyncMock()
    asyncio.run(_aclose_queue_repo_best_effort(mock_repo))
    mock_repo.aclose.assert_awaited_once()


def test_aclose_queue_repo_no_aclose_does_not_raise():
    """Does not raise when repo has no aclose method."""
    mock_repo = MagicMock(spec=[])  # no aclose attribute
    asyncio.run(_aclose_queue_repo_best_effort(mock_repo))  # no raise


def test_aclose_queue_repo_error_logged_does_not_raise():
    """Logs but does not raise when aclose() raises."""
    mock_repo = MagicMock()
    mock_repo.aclose = AsyncMock(side_effect=RuntimeError("connection reset"))
    asyncio.run(_aclose_queue_repo_best_effort(mock_repo))  # no raise
