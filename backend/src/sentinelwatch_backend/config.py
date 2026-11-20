"""
SentinelWatch Backend Configuration Management.

Loads configuration from YAML file with environment variable overrides.
All environment variables use prefix: SW_BACKEND_
"""

import os
from pathlib import Path
from typing import Any, Optional

from ruamel.yaml import YAML
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def load_yaml(path: Path) -> dict:
    """Load a YAML file with ruamel.yaml."""
    yaml_loader = YAML()
    yaml_loader.preserve_quotes = True
    with path.open("r", encoding="utf-8") as f:
        return yaml_loader.load(f) or {}


class ServerConfig(BaseModel):
    """Server configuration."""

    host: str = "127.0.0.1"
    port: int = 8001
    debug: bool = False
    workers: int = 1
    timeout: int = 30
    max_body_size: int = 10485760


class DatabaseConfig(BaseModel):
    """Database configuration."""

    url: str = "sqlite+aiosqlite:///./data/sentinelwatch.db"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False


class TLSConfig(BaseModel):
    """TLS/SSL configuration."""

    enabled: bool = False
    cert_file: str = ""
    key_file: str = ""
    ca_file: str = ""
    require_client_cert: bool = False


class AuthConfig(BaseModel):
    """Authentication configuration."""

    jwt_secret: str = os.getenv("SW_BACKEND_AUTH__JWT_SECRET", "CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    password_hash_algorithm: str = "argon2"
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4
    bcrypt_rounds: int = 12
    mfa_enabled: bool = True
    mfa_issuer: str = "SentinelWatch"

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        placeholder = "CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY"
        if v == placeholder:
            import warnings
            warnings.warn(
                "JWT secret is using the insecure placeholder. Set SW_BACKEND_AUTH__JWT_SECRET.",
                UserWarning,
                stacklevel=2,
            )
        elif len(v) < 32:
            raise ValueError("JWT secret must contain at least 32 characters")
        return v

    @model_validator(mode="after")
    def validate_production_jwt_secret(self) -> "AuthConfig":
        """Reject default JWT secret in production mode.

        Production detection is deferred to BackendConfig because AuthConfig is a
        standalone model that does not have access to ServerConfig. BackendConfig
        performs the same check after assembling the full configuration.
        """
        return self

    @field_validator("password_hash_algorithm")
    @classmethod
    def validate_hash_algorithm(cls, v: str) -> str:
        if v.lower() not in {"argon2", "bcrypt"}:
            raise ValueError("password_hash_algorithm must be 'argon2' or 'bcrypt'")
        return v.lower()


class RateLimitingConfig(BaseModel):
    """Rate limiting configuration."""

    enabled: bool = True
    default_limit: int = 1000
    default_burst: int = 2000
    agent_limit: int = 100
    agent_burst: int = 500
    auth_limit: int = 10
    auth_burst: int = 20
    register_limit: int = 5
    register_burst: int = 10


class CORSConfig(BaseModel):
    """CORS configuration."""

    allow_all: bool = False
    allowed_origins: str = "https://dashboard.sentinelwatch.local"
    allow_credentials: bool = True
    allowed_methods: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    allowed_headers: str = "Authorization,Content-Type,X-Request-ID"

    @property
    def allowed_origins_list(self) -> list[str]:
        if self.allow_all:
            return ["*"]
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def allowed_methods_list(self) -> list[str]:
        return [method.strip() for method in self.allowed_methods.split(",") if method.strip()]

    @property
    def allowed_headers_list(self) -> list[str]:
        return [header.strip() for header in self.allowed_headers.split(",") if header.strip()]


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    file: str = "logs/backend.log"
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


class AuditConfig(BaseModel):
    """Audit logging configuration."""

    enabled: bool = True
    file: str = "logs/audit.log"
    max_size_mb: int = 500
    backup_count: int = 10
    include_bodies: bool = False


class MetricsConfig(BaseModel):
    """Prometheus metrics configuration."""

    enabled: bool = True
    path: str = "/metrics"


class AgentConfigConfig(BaseModel):
    """Agent configuration distribution settings."""

    version: int = 1
    collection_intervals: dict[str, int] = Field(default_factory=lambda: {
        "process": 5,
        "service": 30,
        "startup": 3600,
        "eventlog": 10,
        "health": 60,
        "heartbeat": 30,
        "config": 300,
    })
    batching: dict[str, Any] = Field(default_factory=lambda: {
        "max_size": 100,
        "max_interval": 5.0,
        "compress": True,
        "compression_level": 3,
    })
    eventlog_channels: list[str] = Field(default_factory=lambda: ["Security", "System", "Application"])
    eventlog_event_ids: list[int] = Field(default_factory=lambda: [4688, 4689, 7045, 7036, 4698, 4699, 4700, 4701, 4702])
    process: dict[str, Any] = Field(default_factory=lambda: {
        "collect_cmdline": True,
        "collect_hashes": False,
        "collect_connections": True,
        "min_lifetime": 0,
        "exclude_names": "System,Registry,smss.exe,csrss.exe,wininit.exe,services.exe,lsass.exe,fontdrvhost.exe",
    })
    service: dict[str, Any] = Field(default_factory=lambda: {
        "collect_hashes": False,
        "include_stopped": True,
    })
    startup: dict[str, Any] = Field(default_factory=lambda: {
        "registry": True,
        "scheduled_tasks": True,
        "startup_folders": True,
        "wmi_subscriptions": True,
    })
    redaction: dict[str, Any] = Field(default_factory=lambda: {
        "enabled": True,
    })


class DetectionConfig(BaseModel):
    """Detection engine configuration."""

    enabled: bool = True
    rules_dir: str = "detection-rules"
    evaluation_interval: int = 60
    max_rules_per_record: int = 1000
    dedup_window: int = 3600
    correlation_window: int = 300


class WebSocketConfig(BaseModel):
    """WebSocket configuration."""

    enabled: bool = True
    heartbeat_interval: int = 30
    max_message_size: int = 1048576


class RetentionConfig(BaseModel):
    """Data retention configuration."""

    process_telemetry_days: int = 30
    service_telemetry_days: int = 90
    startup_inventory_days: int = 365
    eventlog_days: int = 365
    alerts_days: int = 365
    evidence_days: int = 365
    audit_logs_days: int = 2555


class FeatureFlagsConfig(BaseModel):
    """Feature flags."""

    agent_auto_registration: bool = True
    detection_rules_api: bool = True
    evidence_storage: bool = True
    websocket_updates: bool = True


class BackendConfig(BaseSettings):
    """Main backend configuration.

    Loads from YAML file, then environment variables (SW_BACKEND_*),
    with environment variables taking precedence.
    """

    model_config = SettingsConfigDict(
        env_prefix="SW_BACKEND_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    tls: TLSConfig = Field(default_factory=TLSConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    rate_limiting: RateLimitingConfig = Field(default_factory=RateLimitingConfig)
    cors: CORSConfig = Field(default_factory=CORSConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    agent_config: AgentConfigConfig = Field(default_factory=AgentConfigConfig)
    agent_enrollment_token: str = ""
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    websocket: WebSocketConfig = Field(default_factory=WebSocketConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    features: FeatureFlagsConfig = Field(default_factory=FeatureFlagsConfig)

    @model_validator(mode="after")
    def validate_production_jwt_secret(self) -> "BackendConfig":
        """Reject the default placeholder JWT secret in production.

        AuthConfig cannot perform this check itself because it has no reference
        to ServerConfig. This validator runs after the full configuration is
        assembled, so it can inspect ``self.server.debug``.
        """
        DEFAULT_SECRET = "CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY"
        if self.auth.jwt_secret == DEFAULT_SECRET:
            is_test = (
                os.getenv("SW_BACKEND_ENVIRONMENT", "").lower() == "test"
                or os.getenv("ENVIRONMENT", "").lower() == "test"
            )
            is_production = (
                self.server.debug is False
                and not is_test
            )
            if is_production:
                raise ValueError(
                    "Production deployment requires SW_BACKEND_AUTH__JWT_SECRET "
                    "environment variable to be set to a strong random value. "
                    "Default placeholder secret not allowed in production."
                )
        return self

    @classmethod
    def load_from_file(cls, config_path: str | Path) -> "BackendConfig":
        """Load configuration from YAML file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        data = load_yaml(path)

        # Environment values must override nested YAML settings.
        jwt_secret = os.getenv("SW_BACKEND_AUTH__JWT_SECRET")
        if jwt_secret:
            data.setdefault("auth", {})["jwt_secret"] = jwt_secret

        return cls(**data)

    @classmethod
    def load(cls, config_path: Optional[str | Path] = None) -> "BackendConfig":
        """Load configuration with precedence: defaults < file < env vars."""
        if config_path:
            return cls.load_from_file(config_path)
        # Try default locations
        for default_path in [
            Path("config/backend.yaml"),
            Path("../config/backend.yaml"),
            Path("/etc/sentinelwatch/backend.yaml"),
        ]:
            if default_path.exists():
                return cls.load_from_file(default_path)
        # No config file found, use defaults + env vars
        return cls()


# Global config instance (lazy-loaded)
_config: Optional[BackendConfig] = None


def get_config(config_path: Optional[str | Path] = None, reload: bool = False) -> BackendConfig:
    """Get global configuration instance."""
    global _config
    if _config is None or reload:
        _config = BackendConfig.load(config_path)
    return _config


def set_config(config: BackendConfig) -> None:
    """Set global configuration instance (for testing)."""
    global _config
    _config = config
