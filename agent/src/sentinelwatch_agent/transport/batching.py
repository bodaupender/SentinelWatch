"""
Telemetry Batching for SentinelWatch Agent.

Handles batching of telemetry records with configurable size and time limits,
compression, and sequence numbering.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..config import AgentConfig, get_config
from ..logging import get_logger
from ..models import TelemetryBatch, TelemetryBase


@dataclass
class BatcherConfig:
    """Configuration for telemetry batcher."""

    max_batch_size: int = 100
    max_batch_interval: float = 5.0  # seconds
    max_pending_records: int = 10000
    compress: bool = True
    compression_level: int = 3

    @classmethod
    def from_agent_config(cls, config: AgentConfig) -> "BatcherConfig":
        """Create config from agent configuration."""
        return cls(
            max_batch_size=config.batching.max_size,
            max_batch_interval=config.batching.max_interval,
            max_pending_records=config.batching.max_pending_records,
            compress=config.batching.compress,
            compression_level=config.batching.compression_level,
        )


@dataclass
class BatcherStats:
    """Statistics for batcher."""

    batches_created: int = 0
    records_batched: int = 0
    batches_sent: int = 0
    records_sent: int = 0
    batches_failed: int = 0
    records_failed: int = 0
    total_compression_ratio: float = 0.0
    avg_batch_size: float = 0.0
    avg_batch_interval_ms: float = 0.0


class TelemetryBatcher:
    """
    Batches telemetry records for efficient transport.

    Collects records until either max_batch_size is reached or
    max_batch_interval expires, then flushes the batch.
    """

    def __init__(
        self,
        telemetry_type: str,
        agent_id: str,
        config: Optional[BatcherConfig] = None,
        agent_config: Optional[AgentConfig] = None,
        auto_flush: bool = True,
    ):
        self.telemetry_type = telemetry_type
        self.agent_id = agent_id
        self.config = config or (BatcherConfig.from_agent_config(agent_config) if agent_config else BatcherConfig())
        self.logger = get_logger(f"sentinelwatch_agent.transport.batcher.{telemetry_type}")

        self._buffer: List[TelemetryBase] = []
        self._sequence = 0
        self._last_flush = time.monotonic()
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        self._auto_flush = auto_flush
        self._lock = asyncio.Lock()
        self.stats = BatcherStats()

    async def start(self) -> None:
        """Start the batcher's flush timer."""
        if self._running:
            return

        self._running = True
        if self._auto_flush:
            self._flush_task = asyncio.create_task(self._flush_loop())
        self.logger.info(
            "batcher_started",
            telemetry_type=self.telemetry_type,
            max_batch_size=self.config.max_batch_size,
            max_batch_interval=self.config.max_batch_interval,
        )

    async def stop(self) -> None:
        """Stop the batcher and flush remaining records."""
        self._running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Only standalone batchers own their flush destination. The multi-batcher
        # uses the agent's HTTP flush loop to drain externally managed buffers.
        if self._auto_flush:
            await self.flush()

        self.logger.info("batcher_stopped", telemetry_type=self.telemetry_type)

    async def add(self, record) -> None:
        """Add a record to the batch buffer."""
        async with self._lock:
            # Assign sequence number
            self._sequence += 1
            record.sequence = self._sequence
            record.agent_id = self.agent_id

            self._buffer.append(record)
            self.stats.records_batched += 1

            # Check if we should flush immediately
            if self._auto_flush and len(self._buffer) >= self.config.max_batch_size:
                await self._flush_locked()

    async def flush(self) -> Optional[TelemetryBatch]:
        """Flush the current buffer and return the batch."""
        async with self._lock:
            return await self._flush_locked()

    async def requeue(self, records: list[TelemetryBase]) -> int:
        """Put a failed batch ahead of newer records, keeping the oldest sequence data first.

        The queue is intentionally bounded. If the bound is exceeded, the oldest records are
        dropped and the count is returned so the agent can expose the loss in logs/health.
        """
        if not records:
            return 0
        async with self._lock:
            combined = sorted([*records, *self._buffer], key=lambda item: item.sequence)
            overflow = max(0, len(combined) - self.config.max_pending_records)
            self._buffer = combined[overflow:]
            self._sequence = max(self._sequence, *(item.sequence for item in combined))
            if overflow:
                self.logger.error(
                    "telemetry_queue_overflow",
                    telemetry_type=self.telemetry_type,
                    dropped_records=overflow,
                    max_pending_records=self.config.max_pending_records,
                )
            return overflow

    async def _flush_locked(self) -> Optional[TelemetryBatch]:
        """Flush buffer (must hold lock)."""
        if not self._buffer:
            return None

        batch = TelemetryBatch(
            agent_id=self.agent_id,
            telemetry_type=self.telemetry_type,
            records=self._buffer.copy(),
            collected_at=datetime.now(timezone.utc),
            compressed=False,  # Will be set by transport
        )

        # Update stats
        now = time.monotonic()
        interval_ms = (now - self._last_flush) * 1000
        self.stats.batches_created += 1
        self.stats.avg_batch_size = (
            (self.stats.avg_batch_size * (self.stats.batches_created - 1) + len(self._buffer))
            / self.stats.batches_created
        )
        self.stats.avg_batch_interval_ms = (
            (self.stats.avg_batch_interval_ms * (self.stats.batches_created - 1) + interval_ms)
            / self.stats.batches_created
        )
        self._last_flush = now

        self._buffer.clear()

        self.logger.debug(
            "batch_created",
            telemetry_type=self.telemetry_type,
            record_count=len(batch.records),
            sequence_start=batch.records[0].sequence if batch.records else 0,
            sequence_end=batch.records[-1].sequence if batch.records else 0,
        )

        return batch

    async def _flush_loop(self) -> None:
        """Background task that flushes on interval."""
        while self._running:
            try:
                await asyncio.sleep(self.config.max_batch_interval)

                async with self._lock:
                    if self._buffer:
                        await self._flush_locked()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "flush_loop_error",
                    telemetry_type=self.telemetry_type,
                    error=str(e),
                    exc_info=True,
                )
                await asyncio.sleep(1)  # Brief pause before retry

    def get_stats(self) -> BatcherStats:
        """Get batcher statistics."""
        return self.stats

    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return len(self._buffer) == 0

    def buffer_size(self) -> int:
        """Get current buffer size."""
        return len(self._buffer)


class MultiTelemetryBatcher:
    """Manages batchers for multiple telemetry types."""

    def __init__(
        self,
        agent_id: str,
        config: Optional[AgentConfig] = None,
    ):
        self.agent_id = agent_id
        self.config = config
        self.logger = get_logger("sentinelwatch_agent.transport.multi_batcher")

        self._batchers: Dict[str, TelemetryBatcher] = {}
        self._running = False

        # Initialize batchers for each telemetry type
        telemetry_types = ["process", "service", "startup", "eventlog"]
        for t in telemetry_types:
            self._batchers[t] = TelemetryBatcher(
                telemetry_type=t,
                agent_id=agent_id,
                agent_config=config,
                auto_flush=False,
            )

    async def start(self) -> None:
        """Start all batchers."""
        if self._running:
            return

        self._running = True
        for batcher in self._batchers.values():
            await batcher.start()

        self.logger.info("multi_batcher_started", telemetry_types=list(self._batchers.keys()))

    async def stop(self) -> None:
        """Stop all batchers."""
        self._running = False

        for batcher in self._batchers.values():
            await batcher.stop()

        self.logger.info("multi_batcher_stopped")

    def get_batcher(self, telemetry_type: str) -> Optional[TelemetryBatcher]:
        """Get batcher for specific telemetry type."""
        return self._batchers.get(telemetry_type)

    async def add_record(self, telemetry_type: str, record: T) -> None:
        """Add a record to the appropriate batcher."""
        batcher = self._batchers.get(telemetry_type)
        if batcher:
            await batcher.add(record)
        else:
            self.logger.warning("unknown_telemetry_type", telemetry_type=telemetry_type)

    async def flush_all(self) -> Dict[str, TelemetryBatch]:
        """Flush all batchers and return their batches."""
        results = {}
        for telemetry_type, batcher in self._batchers.items():
            batch = await batcher.flush()
            if batch:
                results[telemetry_type] = batch
        return results

    async def requeue(self, telemetry_type: str, batch: TelemetryBatch) -> int:
        """Requeue one unsuccessful upload for retry after connectivity returns."""
        batcher = self._batchers.get(telemetry_type)
        if batcher is None:
            self.logger.error("cannot_requeue_unknown_telemetry_type", telemetry_type=telemetry_type)
            return len(batch.records)
        return await batcher.requeue(batch.records)

    def get_all_stats(self) -> Dict[str, BatcherStats]:
        """Get statistics for all batchers."""
        return {t: b.get_stats() for t, b in self._batchers.items()}

    def total_buffered_records(self) -> int:
        """Get total number of records across all buffers."""
        return sum(b.buffer_size() for b in self._batchers.values())
