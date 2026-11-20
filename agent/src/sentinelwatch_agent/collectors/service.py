"""
Service Collector for SentinelWatch Agent.

Collects Windows service telemetry including security configuration auditing.
"""

import asyncio
import hashlib
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psutil
import winreg

from .base import BaseCollector, CollectionResult
from ..config import AgentConfig, get_config
from ..logging import get_logger, LogContext
from ..models import (
    ServiceTelemetry,
    ServiceConfigInfo,
    ServiceHashInfo,
    ServiceSignatureInfo,
    ServiceStatus,
    ServiceStartType,
    ServiceType,
)
from ..models.health import RetryPolicy, CollectionError


class ServiceCollector(BaseCollector[ServiceTelemetry]):
    """Collects Windows service telemetry with security auditing."""

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        super().__init__("service", config, retry_policy)
        self._previous_services: Dict[str, Dict[str, Any]] = {}

    def get_collection_interval(self) -> int:
        """Get service collection interval from config."""
        if self.config:
            return self.config.collection.service
        return 60

    async def collect(self) -> CollectionResult[ServiceTelemetry]:
        """Collect service telemetry."""
        start_time = time.monotonic()
        records: List[ServiceTelemetry] = []
        errors: List[CollectionError] = []
        current_services: Dict[str, Dict[str, Any]] = {}

        try:
            # Get all services using psutil
            services = await asyncio.to_thread(psutil.win_service_iter)

            for service in services:
                try:
                    with LogContext(service_name=service.name()):
                        record = await self._collect_service_info(service)
                        if record:
                            records.append(record)
                            current_services[record.name] = record.model_dump()
                except Exception as e:
                    self.logger.error(
                        "service_collection_error",
                        service_name=service.name() if hasattr(service, 'name') else "unknown",
                        error=str(e),
                        exc_info=True,
                    )
                    errors.append(CollectionError(
                        collector_name=self.name,
                        error_type=type(e).__name__,
                        error_message=f"Error collecting service: {e}",
                        is_recoverable=True,
                    ))

            # Detect new/changed/removed services
            await self._detect_service_changes(current_services)
            self._previous_services = current_services

        except Exception as e:
            self.logger.error(
                "service_collection_failed",
                error=str(e),
                exc_info=True,
            )
            errors.append(CollectionError(
                collector_name=self.name,
                error_type=type(e).__name__,
                error_message=f"Service collection failed: {e}",
                is_recoverable=False,
            ))

        duration_ms = (time.monotonic() - start_time) * 1000

        return CollectionResult(
            records=records,
            errors=errors,
            duration_ms=duration_ms,
            record_count=len(records),
        )

    async def _detect_service_changes(self, current_services: Dict[str, Dict[str, Any]]) -> None:
        """Detect service changes since last collection."""
        previous_names = set(self._previous_services.keys())
        current_names = set(current_services.keys())

        # New services
        new_services = current_names - previous_names
        for name in new_services:
            self.logger.warning(
                "new_service_detected",
                service_name=name,
                display_name=current_services[name].get("display_name"),
                binary_path=current_services[name].get("binary_path"),
            )

        # Removed services
        removed_services = previous_names - current_names
        for name in removed_services:
            self.logger.warning(
                "service_removed",
                service_name=name,
                previous_display_name=self._previous_services[name].get("display_name"),
            )

        # Changed services
        common_services = current_names & previous_names
        for name in common_services:
            current = current_services[name]
            previous = self._previous_services[name]

            # Check for configuration changes
            if current.get("binary_path") != previous.get("binary_path"):
                self.logger.warning(
                    "service_binary_path_changed",
                    service_name=name,
                    old_path=previous.get("binary_path"),
                    new_path=current.get("binary_path"),
                )

            if current.get("start_type") != previous.get("start_type"):
                self.logger.warning(
                    "service_start_type_changed",
                    service_name=name,
                    old_start_type=previous.get("start_type"),
                    new_start_type=current.get("start_type"),
                )

            if current.get("status") != previous.get("status"):
                self.logger.info(
                    "service_status_changed",
                    service_name=name,
                    old_status=previous.get("status"),
                    new_status=current.get("status"),
                )

    async def _collect_service_info(self, service: Any) -> Optional[ServiceTelemetry]:
        """Collect detailed information for a single service."""
        try:
            with LogContext(service_name=service.name()):
                # Get service details
                name = service.name()
                display_name = service.display_name()
                status = service.status()
                start_type = service.start_type()
                binary_path = service.binpath()
                # psutil's WindowsService API does not expose service_type.
                # Preserve the record and mark the field unknown instead of
                # failing collection for every service on Windows.
                service_type_reader = getattr(service, "service_type", None)
                service_type = service_type_reader() if callable(service_type_reader) else 0
                description = service.description()
                username = service.username()
                # psutil does not expose service dependencies, load-order
                # groups, or error-control settings. Keep those optional
                # fields empty rather than dropping the entire service row.
                dependencies = []
                load_order_group = None
                error_control = None

                # Get PID if running
                pid = None
                if status == "running":
                    try:
                        pid = service.pid()
                    except Exception:
                        pass

                # Audit service configuration
                config_audit = await self._audit_service_config(
                    name, binary_path, display_name
                )

                # Compute hashes
                hashes = None
                if self.config and self.config.service.collect_hashes and binary_path:
                    hashes = await self._compute_hashes(binary_path)

                # Get signature info
                signature = None
                if binary_path:
                    signature = await self._get_signature_info(binary_path)

                # Convert Windows constants to strings
                status_values = {
                    "stopped", "start_pending", "stop_pending", "running",
                    "continue_pending", "pause_pending", "paused",
                }
                status_str = status if isinstance(status, str) and status in status_values else ServiceStatus.from_windows_state(status)
                start_type_values = {
                    "boot": "boot", "system": "system", "automatic": "auto",
                    "auto": "auto", "delayed automatic": "delayed_auto",
                    "manual": "manual", "disabled": "disabled",
                }
                start_type_str = start_type_values.get(start_type.lower(), "unknown") if isinstance(start_type, str) else ServiceStartType.from_windows_start_type(start_type)
                service_type_str = ServiceType.from_windows_type(service_type)

                record = ServiceTelemetry(
                    agent_id=self.config.agent.id if self.config and self.config.agent.id else "unknown",
                    collected_at=datetime.now(timezone.utc),
                    sequence=0,  # Will be set by batcher
                    name=name,
                    display_name=display_name,
                    description=description,
                    status=status_str,
                    start_type=start_type_str,
                    service_type=service_type_str,
                    service_account=username,
                    binary_path=binary_path,
                    pid=pid,
                    dependencies=dependencies or [],
                    load_order_group=load_order_group,
                    error_control=error_control,
                    hashes=hashes,
                    signature=signature,
                    config_audit=config_audit,
                    is_complete=True,
                )

                return record

        except Exception as e:
            self.logger.error(
                "service_info_collection_failed",
                service_name=service.name() if hasattr(service, 'name') else "unknown",
                error=str(e),
                exc_info=True,
            )
            return None

    async def _audit_service_config(
        self,
        name: str,
        binary_path: Optional[str],
        display_name: Optional[str],
    ) -> ServiceConfigInfo:
        """Audit service configuration for security issues."""
        audit = ServiceConfigInfo()

        if not binary_path:
            return audit

        audit.binary_path = binary_path

        # Check if path is quoted
        audit.is_path_quoted = binary_path.startswith('"') and binary_path.endswith('"')
        clean_path = binary_path.strip('"')

        # Check for spaces in path
        audit.has_spaces_in_path = " " in clean_path
        audit.is_unquoted_with_spaces = audit.has_spaces_in_path and not audit.is_path_quoted

        # Check if binary exists
        audit.path_exists = os.path.exists(clean_path)

        if audit.path_exists:
            try:
                # Check file permissions
                stat = os.stat(clean_path)
                audit.binary_owner = str(stat.st_uid) if hasattr(stat, 'st_uid') else "unknown"

                # Check if writable by non-admin users
                # On Windows, check if file is writable by Users group
                import stat as stat_module
                if stat.st_mode & stat_module.S_IWOTH:
                    audit.binary_writable_by_user = True

                # Check parent directory
                parent_dir = os.path.dirname(clean_path)
                if parent_dir:
                    parent_stat = os.stat(parent_dir)
                    audit.directory_owner = str(parent_stat.st_uid) if hasattr(parent_stat, 'st_uid') else "unknown"
                    if parent_stat.st_mode & stat_module.S_IWOTH:
                        audit.directory_writable_by_user = True
                    audit.is_in_writable_location = audit.directory_writable_by_user
            except Exception:
                pass

        # Check for suspicious names
        suspicious_keywords = [
            "update", "install", "setup", "config", "temp", "tmp",
            "backup", "old", "copy", "test", "debug", "dev",
        ]
        name_lower = name.lower()
        display_lower = (display_name or "").lower()
        for keyword in suspicious_keywords:
            if keyword in name_lower or keyword in display_lower:
                audit.has_suspicious_name = True
                break

        # Check for suspicious binary names
        if binary_path:
            binary_name = os.path.basename(binary_path).lower()
            suspicious_binary_names = [
                "svchost.exe", "lsass.exe", "csrss.exe", "wininit.exe",
                "services.exe", "smss.exe", "winlogon.exe", "taskhost.exe",
                "dllhost.exe", "rundll32.exe", "regsvr32.exe",
            ]
            if binary_name in suspicious_binary_names:
                # Check if in standard Windows directory
                windows_dirs = [
                    os.environ.get("SystemRoot", "C:\\Windows").lower(),
                    os.environ.get("SystemRoot", "C:\\Windows") + "\\System32".lower(),
                ]
                if not any(clean_path.lower().startswith(d) for d in windows_dirs):
                    audit.has_suspicious_binary_name = True

        return audit

    async def _compute_hashes(self, file_path: str) -> ServiceHashInfo:
        """Compute file hashes asynchronously."""
        try:
            clean_path = file_path.strip('"')
            if not os.path.exists(clean_path):
                return ServiceHashInfo()

            loop = asyncio.get_event_loop()

            def compute():
                sha256_hash = hashlib.sha256()
                md5_hash = hashlib.md5()
                sha1_hash = hashlib.sha1()

                with open(clean_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        sha256_hash.update(chunk)
                        md5_hash.update(chunk)
                        sha1_hash.update(chunk)

                return ServiceHashInfo(
                    sha256=sha256_hash.hexdigest(),
                    md5=md5_hash.hexdigest(),
                    sha1=sha1_hash.hexdigest(),
                )

            return await loop.run_in_executor(None, compute)
        except Exception as e:
            self.logger.debug("hash_computation_failed", path=file_path, error=str(e))
            return ServiceHashInfo()

    async def _get_signature_info(self, file_path: str) -> Optional[ServiceSignatureInfo]:
        """Get digital signature information for a file (Windows)."""
        try:
            clean_path = file_path.strip('"')
            if not os.path.exists(clean_path):
                return None

            # This would use wintrust or similar Windows APIs
            # For now, return basic info
            return ServiceSignatureInfo(
                is_signed=False,
                verification_error="Signature verification not implemented",
            )
        except Exception as e:
            self.logger.debug("signature_check_failed", path=file_path, error=str(e))
            return None
