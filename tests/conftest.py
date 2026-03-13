"""Pytest configuration and fixtures."""

import pytest
from dotenv import load_dotenv

# Load env before app imports so SECRET etc. are available
load_dotenv("envs/local.env")
