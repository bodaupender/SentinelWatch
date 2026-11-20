"""
Tests for SentinelWatch Agent configuration.
"""

import os
import tempfile
from pathlib import Path

import pytest

from sentinelwatch_agent.config import AgentConfig, merge_collection_config


def write_yaml(path, data):
    """Helper to write YAML using ruamel.yaml."""
    from io import StringIO
    from ruamel.yaml import YAML
    yml = YAML()
    stream = StringIO()
    yml.dump(data, stream)
    path.write_text(stream.getvalue())


class TestAgentConfig:
    """Tests for AgentConfig loading and validation."""

    def test_default_config(self):
        """Test default configuration values."""
        config = AgentConfig()

        assert config.backend.url == "http://127.0.0.1:8001"
        assert config.backend.timeout == 30
        assert config.collection.process == 5
        assert config.collection.service == 30
        assert config.collection.heartbeat == 30
        assert config.logging.level == "INFO"
        assert config.health.enabled is True

    def test_server_collection_update_is_validated_and_merged(self):
        config = AgentConfig()

        updated = merge_collection_config(
            config.collection,
            {"process": 3, "service": 15, "unknown_setting": 1},
        )

        assert updated.process == 3
        assert updated.service == 15
        assert updated.heartbeat == config.collection.heartbeat

    def test_server_collection_update_rejects_unsafe_interval(self):
        config = AgentConfig()

        with pytest.raises(ValueError):
            merge_collection_config(config.collection, {"process": 1})

    def test_load_from_yaml_file(self, tmp_path: Path):
        """Test loading configuration from YAML file."""
        config_data = {
            "backend": {
                "url": "https://custom.example.com",
                "timeout": 15,
            },
            "collection": {
                "process": 60,
                "service": 120,
            },
            "logging": {
                "level": "DEBUG",
            },
        }
        config_file = tmp_path / "test_config.yaml"
        write_yaml(config_file, config_data)

        config = AgentConfig.load_from_file(config_file)

        assert config.backend.url == "https://custom.example.com"
        assert config.backend.timeout == 15
        assert config.collection.process == 60
        assert config.collection.service == 120
        assert config.logging.level == "DEBUG"

    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch):
        """Test environment variable overrides."""
        monkeypatch.setenv("SW_AGENT_BACKEND__URL", "https://env.example.com")
        monkeypatch.setenv("SW_AGENT_COLLECTION__PROCESS", "45")
        monkeypatch.setenv("SW_AGENT_LOGGING__LEVEL", "WARNING")

        config = AgentConfig()

        assert config.backend.url == "https://env.example.com"
        assert config.collection.process == 45
        assert config.logging.level == "WARNING"

    def test_env_var_nested_override(self, monkeypatch: pytest.MonkeyPatch):
        """Test nested environment variable overrides with double underscore."""
        monkeypatch.setenv("SW_AGENT_BACKEND__URL", "https://nested.example.com")
        monkeypatch.setenv("SW_AGENT_BATCHING__MAX_SIZE", "200")

        config = AgentConfig()

        assert config.backend.url == "https://nested.example.com"
        assert config.batching.max_size == 200

    def test_invalid_log_level(self):
        """Test that invalid log level raises error."""
        with pytest.raises(ValueError, match="level must be one of"):
            AgentConfig(logging={"level": "INVALID"})

    def test_invalid_log_format(self):
        """Test that invalid log format raises error."""
        with pytest.raises(ValueError, match="format must be 'json' or 'console'"):
            AgentConfig(logging={"format": "invalid"})

    def test_invalid_compression_level(self):
        """Test that invalid compression level raises error."""
        with pytest.raises(ValueError, match="compression_level must be between 1 and 22"):
            AgentConfig(batching={"compression_level": 0})

        with pytest.raises(ValueError, match="compression_level must be between 1 and 22"):
            AgentConfig(batching={"compression_level": 23})

    def test_invalid_start_type(self):
        """Test that invalid service start_type raises error."""
        with pytest.raises(ValueError, match="start_type must be 'auto', 'manual', or 'disabled'"):
            AgentConfig(service_install={"start_type": "invalid"})

    def test_excluded_names_set(self):
        """Test process exclude names parsing."""
        config = AgentConfig(process={"exclude_names": "foo.exe, bar.exe , baz.exe"})

        excluded = config.process.excluded_names_set
        assert "foo.exe" in excluded
        assert "bar.exe" in excluded
        assert "baz.exe" in excluded

    def test_get_data_dir(self, tmp_path: Path):
        """Test data directory path resolution."""
        config = AgentConfig(data_dir=str(tmp_path / "data"))
        data_dir = config.get_data_dir()

        assert data_dir.is_absolute()
        assert data_dir.name == "data"

    def test_get_log_file(self, tmp_path: Path):
        """Test log file path resolution."""
        config = AgentConfig(
            data_dir=str(tmp_path),
            logging={"file": "logs/test.log"},
        )
        log_file = config.get_log_file()

        assert log_file.is_absolute()
        assert log_file.name == "test.log"
        assert log_file.parent.name == "logs"

    def test_get_bookmark_file(self, tmp_path: Path):
        """Test eventlog bookmark file path resolution."""
        config = AgentConfig(
            data_dir=str(tmp_path),
            eventlog={"bookmark_file": "bookmarks.json"},
        )
        bookmark_file = config.get_bookmark_file()

        assert bookmark_file.is_absolute()
        assert bookmark_file.name == "bookmarks.json"

    def test_missing_config_file(self):
        """Test loading from non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            AgentConfig.load_from_file("/nonexistent/config.yaml")

    def test_empty_config_file(self, tmp_path: Path):
        """Test loading from empty YAML file uses defaults."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        config = AgentConfig.load_from_file(config_file)

        assert config.backend.url == "http://127.0.0.1:8001"

    def test_redaction_patterns_default(self):
        """Test default redaction patterns are loaded."""
        config = AgentConfig()

        patterns = config.redaction.patterns
        assert len(patterns) > 0
        # Check some expected patterns
        assert any("password" in p.lower() for p in patterns)
        assert any("token" in p.lower() for p in patterns)
        assert any("api" in p.lower() for p in patterns)

    def test_feature_flags_defaults(self):
        """Test feature flag defaults."""
        config = AgentConfig()

        assert config.features.process_tree is False
        assert config.features.fim is False
        assert config.features.network_flows is False


class TestConfigLoading:
    """Tests for config loading functions."""

    def test_load_without_file(self):
        """Test load() without config file uses defaults."""
        config = AgentConfig.load()
        assert isinstance(config, AgentConfig)

    def test_load_with_file(self, tmp_path: Path):
        """Test load() with explicit config file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("backend:\n  url: https://file.example.com\n")

        config = AgentConfig.load(config_file)
        assert config.backend.url == "https://file.example.com"
