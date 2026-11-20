"""
SentinelWatch Backend Logging Infrastructure.

Structured JSON logging with structlog, configurable output formats,
log rotation, audit logging, and request context binding.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any, Optional

import structlog
from structlog.types import Processor

from .config import BackendConfig, get_config


def setup_logging(config: Optional[BackendConfig] = None) -> None:
    """Configure structured logging for the backend."""
    if config is None:
        config = get_config()

    log_config = config.logging
    log_file = Path(log_config.file) if log_config.file else None

    # Ensure log directory exists
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)

    # Configure standard library logging
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_config.level))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create formatters
    if log_config.format == "json":
        formatter = logging.Formatter(fmt="%(message)s")
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(getattr(logging, log_config.level))
    root_logger.addHandler(console_handler)

    # File handler with rotation
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=log_config.max_size_mb * 1024 * 1024,
            backupCount=log_config.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(getattr(logging, log_config.level))
        root_logger.addHandler(file_handler)

    # Configure structlog
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if log_config.structured:
        processors.append(structlog.processors.dict_tracebacks)
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=False))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_config.level)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def setup_audit_logging(config: Optional[BackendConfig] = None) -> logging.Logger:
    """Configure separate audit logger."""
    if config is None:
        config = get_config()

    audit_config = config.audit
    if not audit_config.enabled:
        # Return a no-op logger
        logger = logging.getLogger("sentinelwatch.audit")
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.CRITICAL + 1)
        return logger

    audit_file = Path(audit_config.file)
    audit_file.parent.mkdir(parents=True, exist_ok=True)

    audit_logger = logging.getLogger("sentinelwatch.audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.handlers.clear()
    audit_logger.propagate = False

    # JSON formatter for audit logs
    formatter = logging.Formatter(fmt="%(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        audit_file,
        maxBytes=audit_config.max_size_mb * 1024 * 1024,
        backupCount=audit_config.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    audit_logger.addHandler(file_handler)

    return audit_logger


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


def get_audit_logger() -> logging.Logger:
    """Get the audit logger instance."""
    return logging.getLogger("sentinelwatch.audit")


class LoggerMixin:
    """Mixin to add structured logging to classes."""

    @property
    def logger(self) -> structlog.BoundLogger:
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__module__ + "." + self.__class__.__name__)
        return self._logger


def bind_context(**kwargs: Any) -> None:
    """Bind context variables to current logging context."""
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys: str) -> None:
    """Unbind context variables."""
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """Clear all context variables."""
    structlog.contextvars.clear_contextvars()


# Context managers for structured logging
class LogContext:
    """Context manager for temporary log context."""

    def __init__(self, **kwargs: Any):
        self.kwargs = kwargs
        self.previous: dict[str, Any] = {}

    def __enter__(self) -> "LogContext":
        self.previous = structlog.contextvars.get_contextvars().copy()
        bind_context(**self.kwargs)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        clear_context()
        for key, value in self.previous.items():
            structlog.contextvars.bind_contextvars(**{key: value})


# Request context binding (for FastAPI middleware)
def bind_request_context(
    request_id: str,
    method: str,
    path: str,
    client_ip: str,
    user_agent: str = "",
    user_id: str = "",
) -> None:
    """Bind request context for logging."""
    bind_context(
        request_id=request_id,
        http_method=method,
        http_path=path,
        client_ip=client_ip,
        user_agent=user_agent,
        user_id=user_id,
    )


# Audit logging helpers
def audit_log(
    action: str,
    actor_type: str,
    actor_id: str,
    resource_type: str = "",
    resource_id: str = "",
    details: dict = None,
    ip_address: str = "",
    user_agent: str = "",
    result: str = "success",
) -> None:
    """Log an audit event."""
    import json
    from datetime import datetime, timezone
    import uuid

    audit_logger = get_audit_logger()

    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details or {},
        "ip_address": ip_address,
        "user_agent": user_agent,
        "result": result,
    }

    audit_logger.info(json.dumps(entry, separators=(",", ":")))


def audit_login(user_id: str, ip: str, user_agent: str, success: bool) -> None:
    """Log authentication event."""
    audit_log(
        action="auth.login",
        actor_type="user",
        actor_id=user_id,
        ip_address=ip,
        user_agent=user_agent,
        result="success" if success else "failure",
    )


def audit_agent_register(agent_id: str, ip: str, success: bool) -> None:
    """Log agent registration event."""
    audit_log(
        action="agent.register",
        actor_type="agent",
        actor_id=agent_id,
        ip_address=ip,
        result="success" if success else "failure",
    )


def audit_alert_action(alert_id: str, user_id: str, action: str, ip: str) -> None:
    """Log alert triage action."""
    audit_log(
        action=f"alert.{action}",
        actor_type="user",
        actor_id=user_id,
        resource_type="alert",
        resource_id=alert_id,
        ip_address=ip,
        result="success",
    )


def audit_rule_change(rule_id: str, user_id: str, action: str, ip: str) -> None:
    """Log detection rule change."""
    audit_log(
        action=f"rule.{action}",
        actor_type="user",
        actor_id=user_id,
        resource_type="rule",
        resource_id=rule_id,
        ip_address=ip,
        result="success",
    )


def audit_config_change(user_id: str, config_type: str, ip: str) -> None:
    """Log configuration change."""
    audit_log(
        action=f"config.{config_type}.change",
        actor_type="user",
        actor_id=user_id,
        resource_type="config",
        resource_id=config_type,
        ip_address=ip,
        result="success",
    )
