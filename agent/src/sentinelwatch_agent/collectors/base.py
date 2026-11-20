"""
Base Collector Class for SentinelWatch Agent.

Provides common functionality for all telemetry collectors.
"""

import time
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Generic, List, Optional, TypeVar
from dataclasses import dataclass

from ..config import AgentConfig, get_config
from ..logging import get_logger, bind_context, LogContext
from ..models import CollectionError, CollectorStats
from ..models.health import RetryPolicy


T = TypeVar("T")


@dataclass
class CollectionResult(Generic[T]):
    """Result of a collection run."""

    records: List[T]
    errors: List[CollectionError]
    duration_ms: float
    record_count: int
    skipped_count: int = 0

    @property
    def is_success(self) -> bool:
        """Whether collection completed without unrecoverable errors."""
        return len([e for e in self.errors if not e.is_recoverable]) == 0

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0


class BaseCollector(ABC, Generic[T]):
    """Base class for all telemetry collectors."""

    def __init__(
        self,
        name: str,
        config: Optional[AgentConfig] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        self.name = name
        self.config = config or get_config()
        self.retry_policy = retry_policy or RetryPolicy()
        self.logger = get_logger(f"sentinelwatch_agent.collectors.{name}")
        self.stats = CollectorStats(collector_name=name)
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._config_changed_event = asyncio.Event()

    @abstractmethod
    async def collect(self) -> CollectionResult[T]:
        """
        Perform a single collection run.

        Returns:
            CollectionResult containing records and any errors.
        """
        pass

    @abstractmethod
    def get_collection_interval(self) -> int:
        """Get the collection interval in seconds from config."""
        pass

    async def run_with_retry(self) -> CollectionResult[T]:
        """
        Run collection with retry logic.

        Returns:
            CollectionResult with records and errors.
        """
        last_error: Optional[Exception] = None

        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                result = await self.collect()
                if result.is_success:
                    if attempt > 0:
                        self.logger.info(
                            "collection_succeeded_after_retry",
                            collector=self.name,
                            attempt=attempt,
                            record_count=result.record_count,
                        )
                    return result
                else:
                    # Collection had non-recoverable errors
                    self.logger.warning(
                        "collection_had_non_recoverable_errors",
                        collector=self.name,
                        attempt=attempt,
                        errors=len(result.errors),
                    )
                    return result

            except Exception as e:
                last_error = e
                self.logger.warning(
                    "collection_attempt_failed",
                    collector=self.name,
                    attempt=attempt + 1,
                    max_attempts=self.retry_policy.max_retries + 1,
                    error=str(e),
                    exc_info=True,
                )

                if attempt < self.retry_policy.max_retries:
                    delay = self.retry_policy.get_delay(attempt)
                    self.logger.debug(
                        "retrying_collection",
                        collector=self.name,
                        delay_seconds=delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    # All retries exhausted
                    error = CollectionError(
                        collector_name=self.name,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        error_details=f"Failed after {self.retry_policy.max_retries + 1} attempts",
                        is_recoverable=False,
                    )
                    self.stats.record_error(error, 0)
                    return CollectionResult(
                        records=[],
                        errors=[error],
                        duration_ms=0,
                        record_count=0,
                    )

        # Should not reach here
        return CollectionResult(records=[], errors=[], duration_ms=0, record_count=0)

    async def run_continuous(self, callback=None) -> None:
        """
        Run collector continuously at configured interval.

        Args:
            callback: Optional async function to call with CollectionResult
        """
        self._running = True
        self._shutdown_event.clear()
        self.logger.info(
            "collector_starting",
            collector=self.name,
            interval_seconds=self.get_collection_interval(),
        )

        try:
            while self._running:
                start_time = time.monotonic()

                try:
                    result = await self.run_with_retry()

                    duration_ms = (time.monotonic() - start_time) * 1000

                    if result.is_success:
                        self.stats.record_success(duration_ms, result.record_count)
                    else:
                        for error in result.errors:
                            self.stats.record_error(error, duration_ms)

                    # Call callback if provided
                    if callback:
                        try:
                            await callback(result)
                        except Exception as e:
                            self.logger.error(
                                "collector_callback_failed",
                                collector=self.name,
                                error=str(e),
                                exc_info=True,
                            )

                except Exception as e:
                    self.logger.error(
                        "collection_run_failed",
                        collector=self.name,
                        error=str(e),
                        exc_info=True,
                    )
                    duration_ms = (time.monotonic() - start_time) * 1000
                    error = CollectionError(
                        collector_name=self.name,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        is_recoverable=False,
                    )
                    self.stats.record_error(error, duration_ms)

                # Wait for next interval or shutdown
                interval = self.get_collection_interval()
                self._config_changed_event.clear()
                try:
                    await asyncio.wait_for(
                        self._config_changed_event.wait(),
                        timeout=interval,
                    )
                    if not self._running:
                        break
                    self.logger.debug(
                        "collection_interval_updated",
                        collector=self.name,
                        interval_seconds=self.get_collection_interval(),
                    )
                except asyncio.TimeoutError:
                    # Normal interval timeout, continue loop
                    pass

        except asyncio.CancelledError:
            self.logger.info("collector_cancelled", collector=self.name)
        except Exception as e:
            self.logger.error(
                "collector_unexpected_error",
                collector=self.name,
                error=str(e),
                exc_info=True,
            )
        finally:
            self._running = False
            self.logger.info("collector_stopped", collector=self.name)

    def stop(self) -> None:
        """Signal collector to stop."""
        self._running = False
        self._shutdown_event.set()
        self._config_changed_event.set()

    def notify_config_changed(self) -> None:
        """Wake the collector so it can use updated configuration promptly."""
        self._config_changed_event.set()

    def is_running(self) -> bool:
        """Check if collector is running."""
        return self._running

    def get_stats(self) -> CollectorStats:
        """Get collector statistics."""
        return self.stats

    def reset_stats(self) -> None:
        """Reset collector statistics."""
        self.stats = CollectorStats(collector_name=self.name)
