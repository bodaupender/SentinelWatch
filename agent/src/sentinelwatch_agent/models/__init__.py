"""
SentinelWatch Agent Telemetry Models.

Typed models for all telemetry data collected by the agent.
"""

from .process import ProcessTelemetry, ProcessTreeNode, ProcessHashInfo, ProcessSignatureInfo
from .service import (
    ServiceTelemetry,
    ServiceConfigInfo,
    ServiceHashInfo,
    ServiceSignatureInfo,
    ServiceStatus,
    ServiceStartType,
    ServiceType,
)
from .startup import StartupTelemetry, StartupSource, REGISTRY_RUN_KEYS
from .eventlog import WindowsEventTelemetry, EventLogChannel, RECOMMENDED_EVENT_IDS
from .health import AgentHealth, CollectorStats, CollectionError, CollectorStatus
from .base import TelemetryBase, TelemetryBatch

__all__ = [
    "ProcessTelemetry",
    "ProcessTreeNode",
    "ProcessHashInfo",
    "ProcessSignatureInfo",
    "ServiceTelemetry",
    "ServiceConfigInfo",
    "ServiceHashInfo",
    "ServiceSignatureInfo",
    "ServiceStatus",
    "ServiceStartType",
    "ServiceType",
    "StartupTelemetry",
    "StartupSource",
    "WindowsEventTelemetry",
    "EventLogChannel",
    "AgentHealth",
    "CollectorStats",
    "CollectionError",
    "CollectorStatus",
    "TelemetryBase",
    "TelemetryBatch",
]
