"""
Pytest configuration for SentinelWatch Agent tests.
"""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sentinelwatch_agent.config import AgentConfig, set_config


@pytest.fixture(autouse=True)
def reset_config():
    """Reset global config before each test."""
    set_config(None)
    yield
    set_config(None)


@pytest.fixture
def minimal_config() -> AgentConfig:
    """Create a minimal valid configuration for testing."""
    return AgentConfig()


@pytest.fixture
def temp_config_file(tmp_path: Path) -> Path:
    """Create a temporary config file for testing."""
    config_content = """
backend:
  url: "https://test.example.com"
  timeout: 10

collection:
  process: 60
  service: 120

logging:
  level: "DEBUG"
  format: "console"
  file: ""
"""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)
    return config_file
