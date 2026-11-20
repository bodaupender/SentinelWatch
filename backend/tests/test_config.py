"""
Tests for SentinelWatch Backend configuration.
"""

import os
import tempfile
from pathlib import Path

import pytest

from sentinelwatch_backend.config import BackendConfig


def write_yaml(path, data):
    """Helper to write YAML using ruamel.yaml."""
    from io import StringIO
    from ruamel.yaml import YAML
    yml = YAML()
    stream = StringIO()
    yml.dump(data, stream)
    path.write_text(stream.getvalue())


class TestBackendConfig:
    """Tests for BackendConfig loading and validation."""

    @pytest.fixture(autouse=True)
    def _isolated_settings_environment(self, monkeypatch: pytest.MonkeyPatch):
        """Keep machine-level deployment variables out of unit tests."""
        monkeypatch.setenv("SW_BACKEND_SERVER__DEBUG", "true")
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("SW_BACKEND_AUTH__JWT_SECRET", raising=False)
    def test_default_config(self):
        """Test default configuration values."""
        config = BackendConfig()

        assert config.server.host == "127.0.0.1"
        assert config.server.port == 8001
        assert config.database.url == "sqlite+aiosqlite:///./data/sentinelwatch.db"
        assert config.auth.jwt_algorithm == "HS256"
        assert config.auth.access_token_expire_minutes == 15
        assert config.logging.level == "INFO"
        assert config.rate_limiting.enabled is True

    def test_load_from_yaml_file(self, tmp_path: Path):
        """Test loading configuration from YAML file."""
        config_data = {
            "server": {
                "host": "127.0.0.1",
                "port": 9000,
                "debug": True,
            },
            "database": {
                "url": "sqlite+aiosqlite:///./test.db",
            },
            "auth": {
                "jwt_secret": "test-secret-long-enough-for-config-validation",
                "access_token_expire_minutes": 30,
            },
        }
        config_file = tmp_path / "test_config.yaml"
        write_yaml(config_file, config_data)

        config = BackendConfig.load_from_file(config_file)

        assert config.server.host == "127.0.0.1"
        assert config.server.port == 9000
        assert config.server.debug is True
        assert config.database.url == "sqlite+aiosqlite:///./test.db"
        assert config.auth.jwt_secret == "test-secret-long-enough-for-config-validation"
        assert config.auth.access_token_expire_minutes == 30

    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch):
        """Test environment variable overrides."""
        monkeypatch.setenv("SW_BACKEND_SERVER__HOST", "192.168.1.100")
        monkeypatch.setenv("SW_BACKEND_SERVER__PORT", "8080")
        monkeypatch.setenv("SW_BACKEND_DATABASE__URL", "postgresql+asyncpg://user:pass@localhost/db")
        monkeypatch.setenv("SW_BACKEND_AUTH__JWT_SECRET", "env-secret-long-enough-for-config-validation")

        config = BackendConfig()

        assert config.server.host == "192.168.1.100"
        assert config.server.port == 8080
        assert config.database.url == "postgresql+asyncpg://user:pass@localhost/db"
        assert config.auth.jwt_secret == "env-secret-long-enough-for-config-validation"


    def test_jwt_secret_env_overrides_yaml(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """A generated local signing key must take precedence over the YAML placeholder."""
        monkeypatch.setenv("SW_BACKEND_AUTH__JWT_SECRET", "a-generated-secret-with-more-than-32-characters")
        config_file = tmp_path / "config.yaml"
        write_yaml(config_file, {"auth": {"jwt_secret": "CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY"}})

        config = BackendConfig.load_from_file(config_file)

        assert config.auth.jwt_secret == "a-generated-secret-with-more-than-32-characters"

    def test_cors_allowed_origins_list(self):
        """Test CORS allowed origins parsing."""
        config = BackendConfig(cors={"allowed_origins": "https://a.com, https://b.com,https://c.com"})

        origins = config.cors.allowed_origins_list
        assert origins == ["https://a.com", "https://b.com", "https://c.com"]

    def test_cors_allow_all(self):
        """Test CORS allow all origins."""
        config = BackendConfig(cors={"allow_all": True})

        assert config.cors.allowed_origins_list == ["*"]

    def test_invalid_log_level(self):
        """Test that invalid log level raises error."""
        with pytest.raises(ValueError, match="level must be one of"):
            BackendConfig(logging={"level": "INVALID"})

    def test_invalid_hash_algorithm(self):
        """Test that invalid password hash algorithm raises error."""
        with pytest.raises(ValueError, match="password_hash_algorithm must be 'argon2' or 'bcrypt'"):
            BackendConfig(auth={"password_hash_algorithm": "md5"})

    def test_jwt_secret_warning(self, caplog: pytest.LogCaptureFixture):
        """Test that default JWT secret triggers warning."""
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = BackendConfig(auth={"jwt_secret": "CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY"})

            # Should have issued a warning
            assert len(w) == 1
            assert "jwt secret" in str(w[0].message).lower()

    def test_cors_methods_headers_parsing(self):
        """Test CORS methods and headers parsing."""
        config = BackendConfig(
            cors={
                "allowed_methods": "GET, POST, PUT",
                "allowed_headers": "Authorization, Content-Type",
            }
        )

        assert config.cors.allowed_methods_list == ["GET", "POST", "PUT"]
        assert config.cors.allowed_headers_list == ["Authorization", "Content-Type"]

    def test_agent_config_defaults(self):
        """Test agent configuration defaults."""
        config = BackendConfig()

        intervals = config.agent_config.collection_intervals
        assert intervals["process"] == 5
        assert intervals["service"] == 30
        assert intervals["heartbeat"] == 30
        assert intervals["startup"] == 3600

        batching = config.agent_config.batching
        assert batching["max_size"] == 100
        assert batching["compress"] is True

    def test_detection_config_defaults(self):
        """Test detection engine configuration defaults."""
        config = BackendConfig()

        assert config.detection.enabled is True
        assert config.detection.rules_dir == "detection-rules"
        assert config.detection.dedup_window == 3600

    def test_feature_flags(self):
        """Test feature flag defaults."""
        config = BackendConfig()

        assert config.features.agent_auto_registration is True
        assert config.features.detection_rules_api is True
        assert config.features.evidence_storage is True
        assert config.features.websocket_updates is True

    def test_missing_config_file(self):
        """Test loading from non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            BackendConfig.load_from_file("/nonexistent/config.yaml")

    def test_empty_config_file(self, tmp_path: Path):
        """Test loading from empty YAML file uses defaults."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")

        config = BackendConfig.load_from_file(config_file)

        assert config.server.port == 8001


class TestConfigLoading:
    """Tests for config loading functions."""

    def test_load_without_file(self):
        """Test load() without config file uses defaults."""
        config = BackendConfig.load()
        assert isinstance(config, BackendConfig)

    def test_load_with_file(self, tmp_path: Path):
        """Test load() with explicit config file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("server:\n  port: 9000\n")

        config = BackendConfig.load(config_file)
        assert config.server.port == 9000
