"""
SentinelWatch Agent Configuration Management.

Loads configuration from YAML file with environment variable overrides.
All environment variables use prefix: SW_AGENT_
"""

import os
from pathlib import Path
from typing import Any, Optional

from ruamel.yaml import YAML
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def load_yaml(path: Path) -> dict:
    """Load a YAML file with ruamel.yaml."""
    yaml_loader = YAML()
    yaml_loader.preserve_quotes = True
    with path.open("r", encoding="utf-8") as f:
        return yaml_loader.load(f) or {}


class BackendConfig(BaseModel):
    """Backend API configuration."""

    url: str = "https://api.sentinelwatch.local"
    api_prefix: str = "/api/v1"
    timeout: int = 30
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0


class TLSConfig(BaseModel):
    """mTLS certificate configuration."""

    cert_file: str = ""
    key_file: str = ""
    ca_file: str = ""
    store_name: str = "MY"
    store_location: str = "CurrentUser"
    pin_sha256: str = ""


class AgentIdentityConfig(BaseModel):
    """Agent identity configuration."""

    id: str = ""
    enrollment_token: str = ""
    hostname: str = ""
    tags: str = ""
    private_key_pem: str = ""


class CollectionConfig(BaseModel):
    """Telemetry collection intervals (seconds)."""

    process: int = Field(default=5, ge=3, le=300)
    service: int = Field(default=30, ge=5, le=3600)
    startup: int = Field(default=3600, ge=30, le=86400)
    eventlog: int = Field(default=10, ge=1, le=3600)
    health: int = Field(default=60, ge=5, le=3600)
    heartbeat: int = Field(default=30, ge=5, le=300)
    config: int = Field(default=300, ge=10, le=3600)


def merge_collection_config(current: CollectionConfig, overrides: Any) -> CollectionConfig:
    """Validate server supplied collection settings against local safety bounds."""
    if not isinstance(overrides, dict):
        raise ValueError("collection_intervals must be an object")
    values = current.model_dump()
    values.update({key: value for key, value in overrides.items() if key in values})
    return CollectionConfig.model_validate(values)


class BatchingConfig(BaseModel):
    """Telemetry batching configuration."""

    max_size: int = 100
    max_interval: float = 5.0
    max_pending_records: int = Field(default=10000, ge=100, le=1000000)
    compress: bool = True
    compression_level: int = 3

    @field_validator("compression_level")
    @classmethod
    def validate_compression_level(cls, v: int) -> int:
        if not 1 <= v <= 22:
            raise ValueError("compression_level must be between 1 and 22")
        return v


class EventLogConfig(BaseModel):
    """Event log collection configuration."""

    channels: list[str] = Field(default_factory=lambda: ["Security", "System", "Application"])
    event_ids: list[int] = Field(default_factory=lambda: [4688, 4689, 7045, 7036, 4698, 4699, 4700, 4701, 4702])
    max_events_per_poll: int = 1000
    bookmark_file: str = "data/eventlog_bookmarks.json"


class ProcessConfig(BaseModel):
    """Process collection configuration."""

    collect_cmdline: bool = True
    collect_hashes: bool = False
    collect_connections: bool = True
    min_lifetime: int = 0
    exclude_names: str = "System,Registry,smss.exe,csrss.exe,wininit.exe,services.exe,lsass.exe,fontdrvhost.exe"

    @property
    def excluded_names_set(self) -> set[str]:
        return {name.strip().lower() for name in self.exclude_names.split(",") if name.strip()}


class ServiceConfig(BaseModel):
    """Service collection configuration."""

    collect_hashes: bool = False
    include_stopped: bool = True


class StartupConfig(BaseModel):
    """Startup inventory collection configuration."""

    registry: bool = True
    scheduled_tasks: bool = True
    startup_folders: bool = True
    wmi_subscriptions: bool = True


class RedactionConfig(BaseModel):
    """Secret redaction configuration."""

    enabled: bool = True
    patterns: list[str] = Field(default_factory=lambda: [
        r"(?i)(--?password\s*[=:])[^\s]+",
        r"(?i)(--?token\s*[=:])[^\s]+",
        r"(?i)(--?key\s*[=:])[^\s]+",
        r"(?i)(--?secret\s*[=:])[^\s]+",
        r"(?i)(api[_-]?key\s*[=:])[^\s]+",
        r"(?i)(access[_-]?token\s*[=:])[^\s]+",
        r"(?i)(auth[_-]?token\s*[=:])[^\s]+",
        r"(?i)(aws[_-]?access[_-]?key[_-]?id\s*[=:])[^\s]+",
        r"(?i)(aws[_-]?secret[_-]?access[_-]?key\s*[=:])[^\s]+",
        r"(?i)(github[_-]?token\s*[=:])[^\s]+",
        r"(?i)(database[_-]?url\s*[=:])[^\s]+",
        r"(?i)(connection[_-]?string\s*[=:])[^\s]+",
        r"(?i)(jdbc:\w+://[^\s]+)",
        r"(?i)(mongodb://[^\s]+)",
        r"(?i)(redis://[^\s]+)",
        r"(?i)(amqp://[^\s]+)",
        r"([A-Za-z0-9+/]{40,}={0,2})",
    ])
    replacement: str = "[REDACTED]"


class HealthConfig(BaseModel):
    """Health monitoring configuration."""

    enabled: bool = True
    cpu_threshold: float = 80.0
    memory_threshold_mb: int = 500
    disk_threshold_gb: float = 1.0
    queue_threshold: int = 1000


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    file: str = "logs/agent.log"
    max_size_mb: int = 100
    backup_count: int = 5
    structured: bool = True

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"level must be one of {valid}")
        return v.upper()

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        if v.lower() not in {"json", "console"}:
            raise ValueError("format must be 'json' or 'console'")
        return v.lower()


class ServiceInstallConfig(BaseModel):
    """Windows service installation configuration."""

    name: str = "SentinelWatchAgent"
    display_name: str = "SentinelWatch Monitoring Agent"
    description: str = "SentinelWatch Windows Endpoint Monitoring Agent"
    start_type: str = "auto"
    account: str = "LocalSystem"
    dependencies: str = ""

    @field_validator("start_type")
    @classmethod
    def validate_start_type(cls, v: str) -> str:
        if v.lower() not in {"auto", "manual", "disabled"}:
            raise ValueError("start_type must be 'auto', 'manual', or 'disabled'")
        return v.lower()


class FeatureFlagsConfig(BaseModel):
    """Feature flags for gradual rollout."""

    process_tree: bool = False
    fim: bool = False
    network_flows: bool = False


class AgentConfig(BaseSettings):
    """Main agent configuration.

    Loads from YAML file, then environment variables (SW_AGENT_*),
    with environment variables taking precedence.
    """

    model_config = SettingsConfigDict(
        env_prefix="SW_AGENT_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    backend: BackendConfig = Field(default_factory=BackendConfig)
    tls: TLSConfig = Field(default_factory=TLSConfig)
    agent: AgentIdentityConfig = Field(default_factory=AgentIdentityConfig)
    collection: CollectionConfig = Field(default_factory=CollectionConfig)
    batching: BatchingConfig = Field(default_factory=BatchingConfig)
    eventlog: EventLogConfig = Field(default_factory=EventLogConfig)
    process: ProcessConfig = Field(default_factory=ProcessConfig)
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    startup: StartupConfig = Field(default_factory=StartupConfig)
    redaction: RedactionConfig = Field(default_factory=RedactionConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    service_install: ServiceInstallConfig = Field(default_factory=ServiceInstallConfig)
    data_dir: str = "data"
    features: FeatureFlagsConfig = Field(default_factory=FeatureFlagsConfig)

    @classmethod
    def load_from_file(cls, config_path: str | Path) -> "AgentConfig":
        """Load configuration from YAML file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        data = load_yaml(path)
        return cls(**data)

    @classmethod
    def load(cls, config_path: Optional[str | Path] = None) -> "AgentConfig":
        """Load configuration with precedence: defaults < file < env vars."""
        if config_path:
            return cls.load_from_file(config_path)
        # Try default locations
        for default_path in [
            Path("config/agent.yaml"),
            Path("../config/agent.yaml"),
            Path("/etc/sentinelwatch/agent.yaml"),
        ]:
            if default_path.exists():
                return cls.load_from_file(default_path)
        # No config file found, use defaults + env vars
        return cls()

    def get_data_dir(self) -> Path:
        """Get absolute data directory path."""
        path = Path(self.data_dir)
        if not path.is_absolute():
            # Relative to current working directory
            path = Path.cwd() / path
        return path

    def get_log_file(self) -> Path:
        """Get absolute log file path."""
        path = Path(self.logging.file)
        if not path.is_absolute():
            path = self.get_data_dir() / path
        return path

    def get_bookmark_file(self) -> Path:
        """Get absolute eventlog bookmark file path."""
        path = Path(self.eventlog.bookmark_file)
        if not path.is_absolute():
            path = self.get_data_dir() / path
        return path


# Global config instance (lazy-loaded)
_config: Optional[AgentConfig] = None


def get_config(config_path: Optional[str | Path] = None, reload: bool = False) -> AgentConfig:
    """Get global configuration instance."""
    global _config
    if _config is None or reload:
        _config = AgentConfig.load(config_path)
    return _config


def set_config(config: AgentConfig) -> None:
    """Set global configuration instance (for testing)."""
    global _config
    _config = config
