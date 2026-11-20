"""
SentinelWatch Agent Logging Infrastructure.

Structured JSON logging with structlog, configurable output formats,
log rotation, and context binding for traceability.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any, Optional

import structlog
from structlog.types import Processor

from .config import AgentConfig, get_config


def setup_logging(config: Optional[AgentConfig] = None) -> None:
    """Configure structured logging for the agent."""
    if config is None:
        config = get_config()

    log_config = config.logging
    log_file = config.get_log_file()

    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Configure standard library logging
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_config.level))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create formatters
    if log_config.format == "json":
        # JSON formatter for structured logging
        formatter = logging.Formatter(
            fmt="%(message)s",  # structlog handles formatting
        )
    else:
        # Console-friendly formatter
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
    if log_config.file:
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


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


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
        # Save current context
        self.previous = structlog.contextvars.get_contextvars().copy()
        # Bind new context
        bind_context(**self.kwargs)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        # Restore previous context
        clear_context()
        for key, value in self.previous.items():
            structlog.contextvars.bind_contextvars(**{key: value})


def log_function_call(logger: structlog.BoundLogger, func_name: str, **kwargs: Any) -> None:
    """Log a function call with parameters."""
    logger.debug("function_call", function=func_name, **kwargs)


def log_function_result(logger: structlog.BoundLogger, func_name: str, result: Any = None, **kwargs: Any) -> None:
    """Log a function result."""
    logger.debug("function_result", function=func_name, result=result, **kwargs)


def log_error(logger: structlog.BoundLogger, error: Exception, context: str = "", **kwargs: Any) -> None:
    """Log an error with full context."""
    logger.error(
        "error",
        error_type=type(error).__name__,
        error_message=str(error),
        context=context,
        **kwargs,
    )


# Startup logging
def log_startup(config: AgentConfig) -> None:
    """Log agent startup information."""
    logger = get_logger("sentinelwatch_agent.startup")
    logger.info(
        "agent_starting",
        version="0.1.0",
        config_file=str(config.get_data_dir() / "config" / "agent.yaml"),
        data_dir=str(config.get_data_dir()),
        log_file=str(config.get_log_file()),
        backend_url=config.backend.url,
        collection_intervals={
            "process": config.collection.process,
            "service": config.collection.service,
            "startup": config.collection.startup,
            "eventlog": config.collection.eventlog,
        },
        batching={
            "max_size": config.batching.max_size,
            "max_interval": config.batching.max_interval,
            "compress": config.batching.compress,
        },
        features=config.features.model_dump(),
    )


def log_shutdown() -> None:
    """Log agent shutdown."""
    logger = get_logger("sentinelwatch_agent.shutdown")
    logger.info("agent_stopping")
