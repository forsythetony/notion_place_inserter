"""Pytest configuration and fixtures."""

import os

import pytest
from dotenv import load_dotenv

# Load env before app imports so secret etc. are available
load_dotenv("envs/local.env")

# App expects "secret" (lowercase); env files often use SECRET
if "secret" not in os.environ and "SECRET" in os.environ:
    os.environ["secret"] = os.environ["SECRET"]
