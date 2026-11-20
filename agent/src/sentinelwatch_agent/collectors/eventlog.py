"""
Windows Event Log Collector for SentinelWatch Agent.

Collects events from Windows Event Log channels with configurable filtering,
bookmark tracking, and duplicate prevention.
"""

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import win32evtlog
    import win32evtlogutil
    _EVENT_LOG_IMPORT_ERROR: Optional[str] = None
except (ImportError, OSError) as import_error:
    # A blocked or unavailable Win32 Event Log DLL must degrade this collector,
    # not prevent process and service monitoring from starting.
    win32evtlog = None  # type: ignore[assignment]
    win32evtlogutil = None  # type: ignore[assignment]
    _EVENT_LOG_IMPORT_ERROR = type(import_error).__name__

from .base import BaseCollector, CollectionResult
from ..config import AgentConfig, get_config
from ..logging import get_logger, LogContext
from ..models import WindowsEventTelemetry, EventLogChannel, RECOMMENDED_EVENT_IDS
from ..models.health import RetryPolicy, CollectionError


class EventLogCollector(BaseCollector[WindowsEventTelemetry]):
    """Collects Windows Event Log telemetry with bookmark-based resumption."""

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        super().__init__("eventlog", config, retry_policy)
        self._bookmarks: Dict[str, int] = {}  # channel -> last record_id
        self._seen_records: Set[Tuple[str, int]] = set()  # (channel, record_id)
        self._bookmark_file: Optional[Path] = None
        self._load_bookmarks()

    def get_collection_interval(self) -> int:
        """Get event log collection interval from config."""
        if self.config:
            return self.config.collection.eventlog
        return 10

    def _load_bookmarks(self) -> None:
        """Load bookmarks from persistent storage."""
        if self.config:
            self._bookmark_file = self.config.get_bookmark_file()
            if self._bookmark_file and self._bookmark_file.exists():
                try:
                    with open(self._bookmark_file, "r") as f:
                        data = json.load(f)
                        self._bookmarks = {k: int(v) for k, v in data.get("bookmarks", {}).items()}
                    self.logger.info("bookmarks_loaded", bookmarks=self._bookmarks)
                except Exception as e:
                    self.logger.warning("bookmark_load_failed", error=str(e))

    def _save_bookmarks(self) -> None:
        """Save bookmarks to persistent storage."""
        if not self._bookmark_file:
            return

        try:
            self._bookmark_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "bookmarks": self._bookmarks,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(self._bookmark_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            self.logger.warning("bookmark_save_failed", error=str(e))

    def get_collection_interval(self) -> int:
        """Get event log collection interval from config."""
        if self.config:
            return self.config.collection.eventlog
        return 10

    async def collect(self) -> CollectionResult[WindowsEventTelemetry]:
        """Collect events from configured Windows Event Log channels."""
        start_time = time.monotonic()
        records: List[WindowsEventTelemetry] = []
        errors: List[CollectionError] = []

        if not self.config:
            errors.append(CollectionError(
                collector_name=self.name,
                error_type="ConfigurationError",
                error_message="No configuration available",
                is_recoverable=False,
            ))
            return CollectionResult(records=[], errors=errors, duration_ms=0, record_count=0)

        if win32evtlog is None or win32evtlogutil is None:
            errors.append(CollectionError(
                collector_name=self.name,
                error_type="WindowsEventLogUnavailable",
                error_message="Windows Event Log APIs could not be loaded; other collectors remain available",
                error_details=_EVENT_LOG_IMPORT_ERROR,
                is_recoverable=False,
            ))
            return CollectionResult(
                records=records,
                errors=errors,
                duration_ms=(time.monotonic() - start_time) * 1000,
                record_count=0,
            )

        # Get configured channels and event IDs
        channels = self.config.eventlog.channels
        event_ids = self.config.eventlog.event_ids
        max_events = self.config.eventlog.max_events_per_poll

        # If no specific event IDs configured, use recommended set
        if not event_ids:
            event_ids = list(RECOMMENDED_EVENT_IDS)

        for channel_name in channels:
            try:
                channel_records, channel_errors = await self._collect_channel(
                    channel_name,
                    set(event_ids),
                    max_events,
                )
                records.extend(channel_records)
                errors.extend(channel_errors)
            except Exception as e:
                self.logger.error(
                    "channel_collection_failed",
                    channel=channel_name,
                    error=str(e),
                    exc_info=True,
                )
                errors.append(CollectionError(
                    collector_name=self.name,
                    error_type=type(e).__name__,
                    error_message=f"Failed to collect from channel {channel_name}: {e}",
                    is_recoverable=True,
                ))

        # Save bookmarks after successful collection
        if records:
            self._save_bookmarks()

        duration_ms = (time.monotonic() - start_time) * 1000

        return CollectionResult(
            records=records,
            errors=errors,
            duration_ms=duration_ms,
            record_count=len(records),
        )

    async def _collect_channel(
        self,
        channel_name: str,
        event_ids: Set[int],
        max_events: int,
    ) -> Tuple[List[WindowsEventTelemetry], List[CollectionError]]:
        """Collect events from a single channel."""
        records: List[WindowsEventTelemetry] = []
        errors: List[CollectionError] = []

        try:
            # Open event log
            handle = await asyncio.to_thread(
                win32evtlog.OpenEventLog,
                None,  # local computer
                channel_name,
            )

            try:
                # Get last record ID from bookmark
                last_record_id = self._bookmarks.get(channel_name, 0)

                # Read events
                flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ

                events_read = 0
                while events_read < max_events:
                    try:
                        events = await asyncio.to_thread(
                            win32evtlog.ReadEventLog,
                            handle,
                            flags,
                            0,
                        )
                    except win32evtlog.error as e:
                        if e.winerror == 183:  # ERROR_NO_MORE_ITEMS
                            break
                        raise

                    if not events:
                        break

                    for event in events:
                        if events_read >= max_events:
                            break

                        try:
                            with LogContext(channel=channel_name, event_id=event.EventID):
                                record = await self._create_event_record(
                                    channel_name,
                                    event,
                                    last_record_id,
                                )
                                if record:
                                    # Check for duplicates
                                    record_key = (channel_name, record.record_id)
                                    if record_key not in self._seen_records:
                                        self._seen_records.add(record_key)
                                        records.append(record)
                                        events_read += 1

                                        # Update bookmark
                                        if record.record_id > last_record_id:
                                            last_record_id = record.record_id
                                            self._bookmarks[channel_name] = last_record_id
                        except Exception as e:
                            self.logger.debug(
                                "event_record_creation_failed",
                                event_id=event.EventID,
                                error=str(e),
                            )

                    # Update bookmark after each batch
                    self._bookmarks[channel_name] = last_record_id

            finally:
                try:
                    await asyncio.to_thread(win32evtlog.CloseEventLog, handle)
                except Exception:
                    pass

        except Exception as e:
            self.logger.error(
                "channel_read_failed",
                channel=channel_name,
                error=str(e),
            )
            errors.append(CollectionError(
                collector_name=self.name,
                error_type=type(e).__name__,
                error_message=f"Failed to read channel {channel_name}: {e}",
                is_recoverable=True,
            ))

        return records, errors

    async def _create_event_record(
        self,
        channel_name: str,
        event: Any,
        last_record_id: int,
    ) -> Optional[WindowsEventTelemetry]:
        """Create telemetry record from Windows event."""
        try:
            # Skip if event ID not in configured list
            if event.EventID not in RECOMMENDED_EVENT_IDS and event.EventID not in (0,):
                return None

            # Skip if record ID is older than bookmark
            if event.RecordNumber <= last_record_id:
                return None

            # Extract event data
            record_id = event.RecordNumber
            event_id = event.EventID
            provider_name = event.SourceName
            computer = event.ComputerName or os.environ.get("COMPUTERNAME", "unknown")

            # Event timestamp
            event_timestamp = datetime.fromtimestamp(
                event.TimeGenerated.timestamp(),
                tz=timezone.utc,
            )

            # Event level
            level_map = {
                win32evtlog.EVENTLOG_SUCCESS: "information",
                win32evtlog.EVENTLOG_ERROR_TYPE: "error",
                win32evtlog.EVENTLOG_WARNING_TYPE: "warning",
                win32evtlog.EVENTLOG_INFORMATION_TYPE: "information",
                win32evtlog.EVENTLOG_AUDIT_SUCCESS: "information",
                win32evtlog.EVENTLOG_AUDIT_FAILURE: "error",
            }
            level = level_map.get(event.EventType, "information")

            # Get message
            message = None
            try:
                message = await asyncio.to_thread(
                    win32evtlogutil.SafeFormatMessage,
                    event,
                    channel_name,
                )
            except Exception:
                pass

            # Get XML representation
            raw_xml = None
            try:
                raw_xml = await asyncio.to_thread(
                    win32evtlogutil.GetEventLogRecord,
                    event,
                )
            except Exception:
                pass

            # User information
            user_sid = None
            user_name = None
            user_domain = None
            if event.Sid:
                try:
                    import win32security
                    name, domain, _ = await asyncio.to_thread(
                        win32security.LookupAccountSid,
                        None,
                        event.Sid,
                    )
                    user_name = name
                    user_domain = domain
                    user_sid = str(event.Sid)
                except Exception:
                    pass

            # Extract structured data based on event ID
            extracted = await self._extract_event_data(event, channel_name, event_id)

            record = WindowsEventTelemetry(
                agent_id=self.config.agent.id if self.config and self.config.agent.id else "unknown",
                collected_at=datetime.now(timezone.utc),
                sequence=0,
                event_id=event_id,
                record_id=record_id,
                channel=channel_name,
                provider_name=provider_name,
                provider_guid=None,
                level=level,
                event_timestamp=event_timestamp,
                computer=computer,
                user_sid=user_sid,
                user_name=user_name,
                user_domain=user_domain,
                message=message,
                raw_xml=raw_xml,
                extracted=extracted,
                is_complete=True,
            )

            # Populate extracted fields for common event types
            await self._populate_extracted_fields(record, event, channel_name, event_id)

            return record

        except Exception as e:
            self.logger.debug(
                "event_record_creation_failed",
                event_id=event.EventID if hasattr(event, 'EventID') else "unknown",
                error=str(e),
            )
            return None

    async def _extract_event_data(
        self,
        event: Any,
        channel: str,
        event_id: int,
    ) -> Dict[str, Any]:
        """Extract structured data from event."""
        extracted = {}

        try:
            # For Security events, StringInserts contains parsed data
            if hasattr(event, 'StringInserts') and event.StringInserts:
                inserts = event.StringInserts
                if isinstance(inserts, (list, tuple)):
                    extracted["string_inserts"] = list(inserts)

            # Extract common fields based on event ID
            if event_id == 4688:  # Process Creation
                # StringInserts for 4688:
                # [0] SubjectUserSid, [1] SubjectUserName, [2] SubjectDomainName, [3] SubjectLogonId
                # [4] NewProcessId, [5] NewProcessName, [6] TokenElevationType, [7] CommandLine
                # [8] TargetUserSid, [9] TargetUserName, [10] TargetDomainName, [11] TargetLogonId
                # [12] ParentProcessId, [13] ParentProcessName, [14] ProcessId
                if hasattr(event, 'StringInserts') and len(event.StringInserts) >= 15:
                    extracted.update({
                        "subject_user_sid": event.StringInserts[0] if len(event.StringInserts) > 0 else None,
                        "subject_user_name": event.StringInserts[1] if len(event.StringInserts) > 1 else None,
                        "subject_domain_name": event.StringInserts[2] if len(event.StringInserts) > 2 else None,
                        "subject_logon_id": event.StringInserts[3] if len(event.StringInserts) > 3 else None,
                        "new_process_id": event.StringInserts[4] if len(event.StringInserts) > 4 else None,
                        "new_process_name": event.StringInserts[5] if len(event.StringInserts) > 5 else None,
                        "token_elevation_type": event.StringInserts[6] if len(event.StringInserts) > 6 else None,
                        "command_line": event.StringInserts[7] if len(event.StringInserts) > 7 else None,
                        "parent_process_id": event.StringInserts[12] if len(event.StringInserts) > 12 else None,
                        "parent_process_name": event.StringInserts[13] if len(event.StringInserts) > 13 else None,
                    })

            elif event_id == 4624:  # Logon
                if hasattr(event, 'StringInserts') and len(event.StringInserts) >= 10:
                    extracted.update({
                        "subject_user_sid": event.StringInserts[0] if len(event.StringInserts) > 0 else None,
                        "subject_user_name": event.StringInserts[1] if len(event.StringInserts) > 1 else None,
                        "subject_domain_name": event.StringInserts[2] if len(event.StringInserts) > 2 else None,
                        "subject_logon_id": event.StringInserts[3] if len(event.StringInserts) > 3 else None,
                        "logon_type": event.StringInserts[8] if len(event.StringInserts) > 8 else None,
                        "target_user_sid": event.StringInserts[4] if len(event.StringInserts) > 4 else None,
                        "target_user_name": event.StringInserts[5] if len(event.StringInserts) > 5 else None,
                        "target_domain_name": event.StringInserts[6] if len(event.StringInserts) > 6 else None,
                        "target_logon_id": event.StringInserts[7] if len(event.StringInserts) > 7 else None,
                        "logon_process": event.StringInserts[9] if len(event.StringInserts) > 9 else None,
                        "authentication_package": event.StringInserts[10] if len(event.StringInserts) > 10 else None,
                    })

            elif event_id == 7045:  # Service Installed
                if hasattr(event, 'StringInserts') and len(event.StringInserts) >= 4:
                    extracted.update({
                        "service_name": event.StringInserts[0] if len(event.StringInserts) > 0 else None,
                        "service_file_name": event.StringInserts[1] if len(event.StringInserts) > 1 else None,
                        "service_type": event.StringInserts[2] if len(event.StringInserts) > 2 else None,
                        "service_start_type": event.StringInserts[3] if len(event.StringInserts) > 3 else None,
                        "service_account": event.StringInserts[4] if len(event.StringInserts) > 4 else None,
                    })

            elif event_id == 4698:  # Scheduled Task Created
                if hasattr(event, 'StringInserts') and len(event.StringInserts) >= 2:
                    extracted.update({
                        "task_name": event.StringInserts[0] if len(event.StringInserts) > 0 else None,
                        "task_content": event.StringInserts[1] if len(event.StringInserts) > 1 else None,
                    })

        except Exception as e:
            self.logger.debug("event_data_extraction_failed", event_id=event_id, error=str(e))

        return extracted

    async def _populate_extracted_fields(
        self,
        record: WindowsEventTelemetry,
        event: Any,
        channel: str,
        event_id: int,
    ) -> None:
        """Populate the extracted fields in the record."""
        try:
            # Process creation events
            if event_id == 4688 and record.extracted:
                ext = record.extracted
                record.process_id = int(ext.get("new_process_id", 0)) if ext.get("new_process_id") else None
                record.process_name = ext.get("new_process_name")
                record.process_command_line = ext.get("command_line")
                record.parent_process_id = int(ext.get("parent_process_id", 0)) if ext.get("parent_process_id") else None
                record.parent_process_name = ext.get("parent_process_name")

            # Service events
            if event_id == 7045 and record.extracted:
                ext = record.extracted
                record.service_name = ext.get("service_name")
                record.service_binary_path = ext.get("service_file_name")
                record.service_account = ext.get("service_account")

            # Scheduled task events
            if event_id == 4698 and record.extracted:
                ext = record.extracted
                record.task_name = ext.get("task_name")

        except Exception as e:
            self.logger.debug("extracted_field_population_failed", error=str(e))
