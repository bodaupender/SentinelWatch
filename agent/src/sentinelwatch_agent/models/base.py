"""
Base models for SentinelWatch Agent telemetry.
"""

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


T = TypeVar("T")


class TelemetryBase(BaseModel):
    """Base class for all telemetry records."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    agent_id: str = Field(..., description="Unique agent identifier")
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Collection timestamp in UTC",
    )
    sequence: int = Field(..., description="Monotonically increasing sequence number")


class TelemetryBatch(BaseModel, Generic[T]):
    """Batch of telemetry records for efficient transport."""

    model_config = ConfigDict(
        extra="forbid",
    )

    agent_id: str = Field(..., description="Agent identifier")
    telemetry_type: str = Field(..., description="Type of telemetry: process, service, startup, eventlog")
    records: list[T] = Field(default_factory=list, description="Telemetry records")
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Batch creation timestamp in UTC",
    )
    compressed: bool = Field(False, description="Whether records are compressed")

    def add_record(self, record: T) -> None:
        """Add a record to the batch."""
        self.records.append(record)

    def __len__(self) -> int:
        return len(self.records)

    def is_empty(self) -> bool:
        return len(self.records) == 0


def generate_record_id() -> str:
    """Generate a unique record ID."""
    return str(uuid4())
