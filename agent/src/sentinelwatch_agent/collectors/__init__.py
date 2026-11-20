"""
SentinelWatch Agent Collectors Package.
"""

from .base import BaseCollector, CollectionResult
from .process import ProcessCollector
from .service import ServiceCollector
from .startup import StartupCollector
from .eventlog import EventLogCollector

__all__ = [
    "BaseCollector",
    "CollectionResult",
    "ProcessCollector",
    "ServiceCollector",
    "StartupCollector",
    "EventLogCollector",
]
