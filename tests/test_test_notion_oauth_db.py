"""Unit tests for scripts/test_notion_oauth_db.py."""

import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "test_notion_oauth_db.py"


def test_script_help_exits_0():
    """Script --help exits successfully."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        cwd=SCRIPTS_DIR.parent,
    )
    assert result.returncode == 0
    assert "OAuth" in result.stdout or "token" in result.stdout.lower()
    assert "--data-source-id" in result.stdout or "data-source-id" in result.stdout


def test_script_exits_1_when_token_empty():
    """Script exits with code 1 when --token is empty."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--token", ""],
        capture_output=True,
        text=True,
        cwd=SCRIPTS_DIR.parent,
    )
    assert result.returncode == 1
    assert "token" in result.stderr.lower() or "NOTION_OAUTH_TEST_TOKEN" in result.stderr
