"""
SentinelWatch Agent - Windows Endpoint Monitoring Agent.

A professional Windows endpoint process and service monitoring platform
with an enterprise-style SOC dashboard.
"""

__version__ = "0.1.0"
__author__ = "SentinelWatch Team"
__license__ = "MIT"

from .config import AgentConfig, get_config
from .health import HealthMetrics, HealthMonitor, get_system_info
from .logging import get_logger, setup_logging
from .models import (
    ProcessTelemetry,
    ServiceTelemetry,
    StartupTelemetry,
    WindowsEventTelemetry,
    AgentHealth,
    CollectorStats,
    CollectionError,
    TelemetryBatch,
    ProcessTreeNode,
    ServiceConfigInfo,
    ProcessHashInfo,
    ProcessSignatureInfo,
    ServiceHashInfo,
    ServiceSignatureInfo,
)

__all__ = [
    "__version__",
    "AgentConfig",
    "get_config",
    "HealthMetrics",
    "HealthMonitor",
    "get_system_info",
    "get_logger",
    "setup_logging",
    "ProcessTelemetry",
    "ServiceTelemetry",
    "StartupTelemetry",
    "WindowsEventTelemetry",
    "AgentHealth",
    "CollectorStats",
    "CollectionError",
    "TelemetryBatch",
    "ProcessTreeNode",
    "ServiceConfigInfo",
    "ProcessHashInfo",
    "ProcessSignatureInfo",
    "ServiceHashInfo",
    "ServiceSignatureInfo",
]
