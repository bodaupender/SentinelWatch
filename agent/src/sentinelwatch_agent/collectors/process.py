"""
Process Collector for SentinelWatch Agent.

Collects process telemetry from Windows endpoints using psutil.
Handles access denied, process termination, missing metadata, and other edge cases.
Never crashes the entire agent because one process cannot be inspected.
"""

import asyncio
import hashlib
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, List, Optional, Set, Tuple

import psutil

from .base import BaseCollector, CollectionResult
from ..config import AgentConfig, get_config
from ..logging import get_logger, LogContext
from ..models import ProcessTelemetry, ProcessHashInfo, ProcessSignatureInfo, ProcessTreeNode
from ..models.health import RetryPolicy, CollectionError


def _pid_changes(previous: Set[int], current: Set[int]) -> Tuple[Set[int], Set[int]]:
    """Return newly observed and disappeared PIDs for one reconciliation pass."""
    return current - previous, previous - current


def _create_termination_records(previous_records, current_records, current_pids, observed_at):
    """Create terminal history rows for exited processes and PID reuse."""
    current_by_pid = {record.pid: record for record in current_records}
    terminated = []
    for pid, previous in previous_records.items():
        current = current_by_pid.get(pid)
        exited = pid not in current_pids
        reused = (
            current is not None
            and previous.create_time is not None
            and current.create_time is not None
            and previous.create_time != current.create_time
        )
        if exited or reused:
            terminated.append(previous.model_copy(update={
                "collected_at": observed_at,
                "terminated_at": observed_at,
            }))
    return terminated


def redact_sensitive_command_line(command_line: str, config: AgentConfig) -> str:
    """Apply configured secret patterns when command-line redaction is enabled."""
    redaction = config.redaction
    if not redaction.enabled:
        return command_line
    for pattern in redaction.patterns:
        command_line = re.sub(pattern, redaction.replacement, command_line, flags=re.IGNORECASE)
    return command_line


class ProcessCollector(BaseCollector[ProcessTelemetry]):
    """Collects process telemetry from Windows endpoints using psutil."""

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        super().__init__("process", config, retry_policy)
        self._previous_pids: Set[int] = set()
        self._previous_records = {}
        self._excluded_names: Set[str] = set()

        if self.config:
            self._excluded_names = self.config.process.excluded_names_set

    def get_collection_interval(self) -> int:
        """Get process collection interval from config."""
        if self.config:
            return self.config.collection.process
        return 30

    async def collect(self) -> CollectionResult[ProcessTelemetry]:
        """Collect process telemetry from all running processes."""
        start_time = time.monotonic()
        records: List[ProcessTelemetry] = []
        errors: List[CollectionError] = []
        # Get all PIDs
        try:
            all_pids_raw = await asyncio.to_thread(psutil.pids)
            # psutil.pids can return int on some Python versions, convert to list
            all_pids = list(all_pids_raw) if isinstance(all_pids_raw, (list, tuple)) else [all_pids_raw]
            self.logger.debug("process_enumeration", total_pids=len(all_pids))
        except (psutil.AccessDenied, psutil.Error) as e:
            errors.append(CollectionError(
                collector_name=self.name,
                error_type="ProcessAccessDenied",
                error_message=f"Cannot enumerate processes: {e}",
                is_recoverable=True,
            ))
            return CollectionResult(records=[], errors=errors, duration_ms=0, record_count=0)

        # Compute the reconciliation once from the complete PID snapshot.
        current_pids: Set[int] = set(all_pids)
        new_pids, terminated_pids = _pid_changes(self._previous_pids, current_pids)

        try:
            for pid in all_pids:
                try:
                    # Recreate Process objects every pass. Retaining a PID-keyed
                    # object indefinitely can bind later observations to a PID
                    # that Windows has already reused for another process.
                    process = await asyncio.to_thread(psutil.Process, pid)

                    try:
                        record = await self._collect_process_info(process, pid)
                        if record:
                            records.append(record)
                    except Exception as e:
                        self.logger.error(
                            "process_info_collection_failed",
                            pid=pid,
                            error=str(e),
                            exc_info=True,
                        )
                        errors.append(CollectionError(
                            collector_name=self.name,
                            error_type="CollectionError",
                            error_message=f"Error collecting process {pid}: {e}",
                            is_recoverable=False,
                        ))

                except psutil.NoSuchProcess:
                    # The PID vanished after enumeration; record that race as a
                    # termination only if it was observed in an earlier pass.
                    new_pids.discard(pid)
                    if pid in self._previous_pids:
                        terminated_pids.add(pid)
                    current_pids.discard(pid)
                    errors.append(CollectionError(
                        collector_name=self.name,
                        error_type="ProcessTerminated",
                        error_message=f"Process {pid} exited during collection",
                        is_recoverable=True,
                    ))
                    continue
                except (psutil.AccessDenied, PermissionError):
                    errors.append(CollectionError(
                        collector_name=self.name,
                        error_type="ProcessAccessDenied",
                        error_message=f"Access denied while collecting process {pid}",
                        is_recoverable=True,
                    ))
                    continue
                except Exception as e:
                    self.logger.error(
                        "unexpected_process_error",
                        pid=pid,
                        error=str(e),
                        exc_info=True,
                    )
                    errors.append(CollectionError(
                        collector_name=self.name,
                        error_type="UnexpectedError",
                        error_message=f"Unexpected error for process {pid}: {e}",
                        is_recoverable=False,
                    ))

            # Update tracking state
            self._previous_pids = current_pids

            # Log new/terminated processes
            if new_pids:
                self.logger.info(
                    "process_created",
                    new_pids=list(new_pids),
                    count=len(new_pids),
                )
            if terminated_pids:
                self.logger.info(
                    "process_terminated",
                    terminated_pids=list(terminated_pids),
                    count=len(terminated_pids),
                )

        except Exception as e:
            self.logger.error(
                "process_collection_failed",
                error=str(e),
                exc_info=True,
            )
            errors.append(CollectionError(
                collector_name=self.name,
                error_type="CollectionFailed",
                error_message=f"Process collection failed: {e}",
                is_recoverable=False,
            ))

        duration_ms = (time.monotonic() - start_time) * 1000

        # Preserve termination events separately from active observations. PID plus
        # process creation time is the stable identity because Windows can reuse PIDs.
        current_records = list(records)
        records.extend(_create_termination_records(
            self._previous_records,
            current_records,
            current_pids,
            datetime.now(timezone.utc),
        ))
        for pid in list(self._previous_records):
            if pid not in current_pids:
                self._previous_records.pop(pid, None)
        self._previous_records.update({record.pid: record for record in current_records})

        # Deduplicate active observations by PID (in case of race conditions).
        seen_pids: Set[Tuple[int, Optional[datetime], bool]] = set()
        unique_records: List[ProcessTelemetry] = []
        for record in records:
            identity = (record.pid, record.create_time, record.terminated_at is not None)
            if identity not in seen_pids:
                seen_pids.add(identity)
                unique_records.append(record)

        return CollectionResult(
            records=unique_records,
            errors=errors,
            duration_ms=duration_ms,
            record_count=len(unique_records),
        )

    async def _collect_process_info(self, proc: psutil.Process, pid: int) -> Optional[ProcessTelemetry]:
        """Collect detailed information for a single process."""
        try:
            with LogContext(pid=pid):
                # Basic info - gather concurrently
                name = await asyncio.to_thread(proc.name)
                exe = await asyncio.to_thread(proc.exe)
                cmdline = await asyncio.to_thread(proc.cmdline)
                username = await asyncio.to_thread(proc.username)
                create_time = await asyncio.to_thread(proc.create_time)
                ppid = await asyncio.to_thread(proc.ppid)
                status = await asyncio.to_thread(proc.status)
                cpu_percent = await asyncio.to_thread(proc.cpu_percent, interval=0.0)
                mem_info = await asyncio.to_thread(proc.memory_info)
                num_threads = await asyncio.to_thread(proc.num_threads)
                num_handles = None
                get_num_handles = getattr(proc, "num_handles", None)
                if callable(get_num_handles):
                    try:
                        num_handles = await asyncio.to_thread(get_num_handles)
                    except (psutil.Error, NotImplementedError, AttributeError):
                        # Handle counts are Windows-only and may be unavailable to
                        # the configured service account. Do not invent a value.
                        pass

                # Handle command line - may contain sensitive data
                cmdline_str = None
                if cmdline:
                    cmdline_str = " ".join(cmdline) if self.config and self.config.process.collect_cmdline else None

                # Redact sensitive data if configured
                if cmdline_str and self.config and self.config.process.collect_cmdline:
                    cmdline_str = redact_sensitive_command_line(cmdline_str, self.config)

                # Process tree info
                parent_name = None
                parent_exe = None
                try:
                    parent = await asyncio.to_thread(proc.parent)
                    if parent:
                        parent_name = await asyncio.to_thread(parent.name)
                        parent_exe = await asyncio.to_thread(parent.exe)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

                # Compute hashes (only if exe is available and collect_hashes is True)
                hashes = None
                if self.config and self.config.process.collect_hashes and exe and os.path.exists(exe):
                    hashes = await self._compute_hashes(exe)

                # Signature info
                signature = None
                if exe and os.path.exists(exe):
                    signature = await self._get_signature_info(exe)

                # Memory values
                memory_rss = mem_info.rss
                memory_vms = mem_info.vms
                memory_percent = await asyncio.to_thread(proc.memory_percent)

                # Network connections (optional)
                connections = None
                if self.config and self.config.process.collect_connections:
                    try:
                        conns = await asyncio.to_thread(proc.connections, kind="inet")
                        connections = [
                            {
                                "local_address": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else None,
                                "remote_address": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else None,
                                "status": c.status,
                                "family": str(c.family),
                                "type": str(c.type),
                            }
                            for c in conns
                        ]
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        pass

                # Integrity level (Windows only - may not be available)
                import platform
                integrity_level = None
                if platform.system() == "Windows":
                    try:
                        import win32security
                        sd = psutil.win32security.GetSecurityInfo(
                            exe or "",
                            psutil.win32security.SE_OBJECT_ALL,
                            psutil.win32security.DACL_SECURITY_INFORMATION
                        )
                        # Simplified - would need full security descriptor parsing
                        integrity_level = "Medium"  # default
                    except Exception:
                        pass

                # Capture observation time before collecting detailed info
                observed_at = datetime.now(timezone.utc)

                # Build telemetry record
                record = ProcessTelemetry(
                    agent_id=self.config.agent.id if self.config and self.config.agent.id else "unknown",
                    collected_at=datetime.now(timezone.utc),
                    observed_at=observed_at,
                    sequence=0,  # Will be set by batcher
                    pid=pid,
                    ppid=ppid,
                    name=name or "unknown",
                    exe=exe,
                    cmdline=cmdline_str,
                    username=username,
                    create_time=datetime.fromtimestamp(create_time, tz=timezone.utc) if create_time else None,
                    cpu_percent=cpu_percent,
                    memory_percent=memory_percent,
                    memory_rss_bytes=memory_rss,
                    memory_vms_bytes=memory_vms,
                    num_threads=num_threads,
                    num_handles=num_handles,
                    status=status,
                    integrity_level=integrity_level,
                    connections=connections,
                    hashes=hashes,
                    signature=signature,
                    parent_name=parent_name,
                    parent_exe=parent_exe,
                    is_complete=True,
                )

                return record

        except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError) as e:
            self.logger.debug(
                "process_info_collection_failed",
                pid=pid,
                error=str(e),
            )
            return None
        except Exception as e:
            self.logger.error(
                "unexpected_process_info_error",
                pid=pid,
                error=str(e),
            )
            return None

    async def _compute_hashes(self, file_path: str) -> Optional[ProcessHashInfo]:
        """Compute file hashes asynchronously."""
        try:
            loop = asyncio.get_event_loop()

            def compute():
                sha256_hash = hashlib.sha256()
                md5_hash = hashlib.md5()
                sha1_hash = hashlib.sha1()

                block_size = 1024 * 1024  # 1 MB chunks
                with open(file_path, "rb") as f:
                    while True:
                        data = f.read(block_size)
                        if not data:
                            break
                        sha256_hash.update(data)
                        md5_hash.update(data)
                        sha1_hash.update(data)

                return ProcessHashInfo(
                    sha256=sha256_hash.hexdigest(),
                    md5=md5_hash.hexdigest(),
                    sha1=sha1_hash.hexdigest(),
                )

            return await loop.run_in_executor(None, compute)
        except Exception as e:
            self.logger.debug("hash_computation_failed", path=file_path, error=str(e))
            return None

    async def _get_signature_info(self, file_path: str) -> Optional[ProcessSignatureInfo]:
        """Get digital signature information for a file (Windows)."""
        try:
            # Use winvertrust or similar for proper signature verification
            # For now, return basic info
            return ProcessSignatureInfo(
                is_signed=False,
                verification_error="Signature verification not fully implemented",
            )
        except Exception as e:
            self.logger.debug("signature_check_failed", path=file_path, error=str(e))
            return None
