"""
Startup Inventory Collector for SentinelWatch Agent.

Collects startup entries from various Windows locations:
- Registry Run/RunOnce keys
- Startup folders
- Scheduled tasks
- WMI subscriptions
"""

import asyncio
import hashlib
import os
import time
import winreg
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseCollector, CollectionResult
from ..config import AgentConfig, get_config
from ..logging import get_logger, LogContext
from ..models import StartupTelemetry, StartupSource, REGISTRY_RUN_KEYS
from ..models.health import RetryPolicy, CollectionError


class StartupCollector(BaseCollector[StartupTelemetry]):
    """Collects startup inventory from Windows endpoints."""

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        super().__init__("startup", config, retry_policy)
        self._previous_entries: Dict[str, Dict[str, Any]] = {}

    def get_collection_interval(self) -> int:
        """Get startup collection interval from config."""
        if self.config:
            return self.config.collection.startup
        return 3600  # 1 hour default

    async def collect(self) -> CollectionResult[StartupTelemetry]:
        """Collect startup inventory from all sources."""
        start_time = time.monotonic()
        records: List[StartupTelemetry] = []
        errors: List[CollectionError] = []
        current_entries: Dict[str, Dict[str, Any]] = {}

        try:
            # Collect from registry Run keys
            if self.config and self.config.startup.registry:
                registry_records, registry_errors = await self._collect_registry_entries()
                records.extend(registry_records)
                errors.extend(registry_errors)

            # Collect from startup folders
            if self.config and self.config.startup.startup_folders:
                folder_records, folder_errors = await self._collect_startup_folders()
                records.extend(folder_records)
                errors.extend(folder_errors)

            # Collect from scheduled tasks
            if self.config and self.config.startup.scheduled_tasks:
                task_records, task_errors = await self._collect_scheduled_tasks()
                records.extend(task_records)
                errors.extend(task_errors)

            # Collect WMI subscriptions
            if self.config and self.config.startup.wmi_subscriptions:
                wmi_records, wmi_errors = await self._collect_wmi_subscriptions()
                records.extend(wmi_records)
                errors.extend(wmi_errors)

            # Track current entries for change detection
            for record in records:
                key = f"{record.source.value}:{record.name}:{record.source_key}"
                current_entries[key] = record.model_dump()

            # Detect changes
            await self._detect_changes(current_entries)
            self._previous_entries = current_entries

        except Exception as e:
            self.logger.error(
                "startup_collection_failed",
                error=str(e),
                exc_info=True,
            )
            errors.append(CollectionError(
                collector_name=self.name,
                error_type=type(e).__name__,
                error_message=f"Startup collection failed: {e}",
                is_recoverable=False,
            ))

        duration_ms = (time.monotonic() - start_time) * 1000

        return CollectionResult(
            records=records,
            errors=errors,
            duration_ms=duration_ms,
            record_count=len(records),
        )

    async def _collect_registry_entries(
        self,
    ) -> Tuple[List[StartupTelemetry], List[CollectionError]]:
        """Collect startup entries from registry Run keys."""
        records: List[StartupTelemetry] = []
        errors: List[CollectionError] = []

        for key_path in REGISTRY_RUN_KEYS:
            try:
                hive_name = "HKLM"
                if key_path.startswith("SOFTWARE\\WOW6432Node"):
                    hive_name = "HKLM (WOW6432)"
                elif "CurrentVersion\\Run" in key_path and "WOW6432" not in key_path:
                    hive_name = "HKLM"
                elif "CurrentUser" in key_path:
                    hive_name = "HKCU"

                entries, reg_errors = await self._read_registry_key(
                    hive_name,
                    key_path,
                    StartupSource.REGISTRY_RUN if "Run" in key_path and "RunOnce" not in key_path else StartupSource.REGISTRY_RUN_ONCE,
                )
                records.extend(entries)
                errors.extend(reg_errors)

            except Exception as e:
                self.logger.debug(
                    "registry_key_read_failed",
                    key_path=key_path,
                    error=str(e),
                )
                errors.append(CollectionError(
                    collector_name=self.name,
                    error_type="RegistryAccessError",
                    error_message=f"Failed to read registry key {key_path}: {e}",
                    is_recoverable=True,
                ))

        return records, errors

    async def _read_registry_key(
        self,
        hive_name: str,
        key_path: str,
        source: StartupSource,
    ) -> Tuple[List[StartupTelemetry], List[CollectionError]]:
        """Read values from a registry key."""
        records: List[StartupTelemetry] = []
        errors: List[CollectionError] = []

        # Map hive name to winreg constant
        hive_map = {
            "HKLM": winreg.HKEY_LOCAL_MACHINE,
            "HKCU": winreg.HKEY_CURRENT_USER,
            "HKLM (WOW6432)": winreg.HKEY_LOCAL_MACHINE,
        }

        hive = hive_map.get(hive_name)
        if not hive:
            return records, errors

        try:
            # Open key with appropriate access
            access = winreg.KEY_READ | winreg.KEY_WOW64_64KEY if "WOW6432" in hive_name else winreg.KEY_READ
            key = await asyncio.to_thread(winreg.OpenKey, hive, key_path, 0, access)

            try:
                i = 0
                while True:
                    try:
                        name, value, value_type = await asyncio.to_thread(winreg.EnumValue, key, i)
                        i += 1

                        with LogContext(registry_key=key_path, value_name=name):
                            record = await self._create_registry_record(
                                hive_name, key_path, name, value, value_type, source
                            )
                            if record:
                                records.append(record)
                    except OSError as e:
                        if e.winerror == 259:  # ERROR_NO_MORE_ITEMS
                            break
                        raise
            except FileNotFoundError:
                # Key doesn't exist - not an error
                pass
            except PermissionError as e:
                errors.append(CollectionError(
                    collector_name=self.name,
                    error_type="RegistryPermissionError",
                    error_message=f"Permission denied reading {key_path}: {e}",
                    is_recoverable=True,
                ))
            except Exception as e:
                errors.append(CollectionError(
                    collector_name=self.name,
                    error_type=type(e).__name__,
                    error_message=f"Error reading registry key {key_path}: {e}",
                    is_recoverable=True,
                ))
            finally:
                try:
                    await asyncio.to_thread(winreg.CloseKey, key)
                except Exception:
                    pass

        except Exception as e:
            errors.append(CollectionError(
                collector_name=self.name,
                error_type=type(e).__name__,
                error_message=f"Failed to open registry key {key_path}: {e}",
                is_recoverable=True,
            ))

        return records, errors

    async def _create_registry_record(
        self,
        hive_name: str,
        key_path: str,
        name: str,
        value: str,
        value_type: int,
        source: StartupSource,
    ) -> Optional[StartupTelemetry]:
        """Create a startup telemetry record from registry value."""
        try:
            # Parse command to extract executable and arguments
            executable_path = None
            arguments = None
            command = value

            if value:
                # Handle quoted paths
                if value.startswith('"'):
                    end_quote = value.find('"', 1)
                    if end_quote > 0:
                        executable_path = value[1:end_quote]
                        arguments = value[end_quote + 1:].strip()
                    else:
                        executable_path = value
                else:
                    parts = value.split(None, 1)
                    executable_path = parts[0]
                    arguments = parts[1] if len(parts) > 1 else None

                # Expand environment variables
                if executable_path:
                    executable_path = os.path.expandvars(executable_path)

            # Compute hash if executable exists
            exe_sha256 = None
            exe_md5 = None
            if executable_path and os.path.exists(executable_path):
                exe_sha256, exe_md5 = await self._compute_hashes(executable_path)

            # Check signature
            is_signed = False
            signer_name = None
            if executable_path and os.path.exists(executable_path):
                is_signed, signer_name = await self._check_signature(executable_path)

            record = StartupTelemetry(
                agent_id=self.config.agent.id if self.config and self.config.agent.id else "unknown",
                collected_at=datetime.now(timezone.utc),
                sequence=0,
                source=source,
                source_key=key_path,
                name=name,
                command=command,
                arguments=arguments,
                user_context=hive_name,
                executable_path=executable_path,
                working_directory=os.path.dirname(executable_path) if executable_path else None,
                exe_sha256=exe_sha256,
                exe_md5=exe_md5,
                is_signed=is_signed,
                signer_name=signer_name,
                enabled=True,
                registry_hive=hive_name,
                registry_key_path=key_path,
                registry_value_type=self._get_registry_value_type_name(value_type),
                is_complete=True,
            )

            return record
        except Exception as e:
            self.logger.debug(
                "registry_record_creation_failed",
                name=name,
                error=str(e),
            )
            return None

    def _get_registry_value_type_name(self, value_type: int) -> str:
        """Get registry value type name."""
        types = {
            winreg.REG_SZ: "REG_SZ",
            winreg.REG_EXPAND_SZ: "REG_EXPAND_SZ",
            winreg.REG_BINARY: "REG_BINARY",
            winreg.REG_DWORD: "REG_DWORD",
            winreg.REG_MULTI_SZ: "REG_MULTI_SZ",
            winreg.REG_QWORD: "REG_QWORD",
        }
        return types.get(value_type, f"UNKNOWN({value_type})")

    async def _collect_startup_folders(
        self,
    ) -> Tuple[List[StartupTelemetry], List[CollectionError]]:
        """Collect startup entries from user and common startup folders."""
        records: List[StartupTelemetry] = []
        errors: List[CollectionError] = []

        startup_folders = [
            (Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup", StartupSource.STARTUP_FOLDER_USER),
            (Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup", StartupSource.STARTUP_FOLDER_COMMON),
        ]

        for folder_path, source in startup_folders:
            try:
                if not folder_path.exists():
                    continue

                for item in folder_path.iterdir():
                    try:
                        if item.is_file() or item.is_symlink():
                            with LogContext(startup_item=str(item)):
                                record = await self._create_shortcut_record(item, source)
                                if record:
                                    records.append(record)
                    except Exception as e:
                        self.logger.debug(
                            "startup_folder_item_failed",
                            item=str(item),
                            error=str(e),
                        )
            except Exception as e:
                errors.append(CollectionError(
                    collector_name=self.name,
                    error_type=type(e).__name__,
                    error_message=f"Error reading startup folder {folder_path}: {e}",
                    is_recoverable=True,
                ))

        return records, errors

    async def _create_shortcut_record(
        self,
        file_path: Path,
        source: StartupSource,
    ) -> Optional[StartupTelemetry]:
        """Create startup record from shortcut or executable file."""
        try:
            # For .lnk files, we'd need to resolve the target
            # For now, treat as direct executable
            executable_path = str(file_path)
            name = file_path.stem
            command = str(file_path)

            # Compute hashes
            exe_sha256 = None
            exe_md5 = None
            if os.path.exists(executable_path):
                exe_sha256, exe_md5 = await self._compute_hashes(executable_path)

            is_signed = False
            signer_name = None
            if os.path.exists(executable_path):
                is_signed, signer_name = await self._check_signature(executable_path)

            record = StartupTelemetry(
                agent_id=self.config.agent.id if self.config and self.config.agent.id else "unknown",
                collected_at=datetime.now(timezone.utc),
                sequence=0,
                source=source,
                source_key=str(file_path.parent),
                name=name,
                command=command,
                arguments=None,
                executable_path=executable_path,
                working_directory=str(file_path.parent),
                exe_sha256=exe_sha256,
                exe_md5=exe_md5,
                is_signed=is_signed,
                signer_name=signer_name,
                enabled=True,
                is_complete=True,
            )

            return record
        except Exception as e:
            self.logger.debug(
                "shortcut_record_failed",
                file=str(file_path),
                error=str(e),
            )
            return None

    async def _collect_scheduled_tasks(
        self,
    ) -> Tuple[List[StartupTelemetry], List[CollectionError]]:
        """Collect scheduled tasks using COM interface."""
        records: List[StartupTelemetry] = []
        errors: List[CollectionError] = []

        try:
            # Use schtasks command for compatibility
            import subprocess
            result = await asyncio.to_thread(
                subprocess.run,
                ["schtasks", "/query", "/fo", "csv", "/v"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                errors.append(CollectionError(
                    collector_name=self.name,
                    error_type="ScheduledTaskQueryFailed",
                    error_message=f"schtasks failed: {result.stderr}",
                    is_recoverable=True,
                ))
                return records, errors

            # Parse CSV output
            import csv
            import io
            reader = csv.DictReader(io.StringIO(result.stdout))

            for row in reader:
                try:
                    with LogContext(task_name=row.get("TaskName", "")):
                        record = await self._create_task_record(row)
                        if record:
                            records.append(record)
                except Exception as e:
                    self.logger.debug(
                        "scheduled_task_record_failed",
                        task=row.get("TaskName", ""),
                        error=str(e),
                    )

        except subprocess.TimeoutExpired:
            errors.append(CollectionError(
                collector_name=self.name,
                error_type="ScheduledTaskTimeout",
                error_message="schtasks query timed out",
                is_recoverable=True,
            ))
        except Exception as e:
            errors.append(CollectionError(
                collector_name=self.name,
                error_type=type(e).__name__,
                error_message=f"Scheduled task collection failed: {e}",
                is_recoverable=True,
            ))

        return records, errors

    async def _create_task_record(self, row: Dict[str, str]) -> Optional[StartupTelemetry]:
        """Create startup record from scheduled task."""
        try:
            task_name = row.get("TaskName", "").strip("\\")
            if not task_name:
                return None

            # Get executable path from task actions
            executable_path = row.get("Executable", "") or row.get("Task To Run", "")
            if executable_path:
                executable_path = executable_path.strip('"')

            arguments = row.get("Arguments", "") or None

            # Compute hashes
            exe_sha256 = None
            exe_md5 = None
            if executable_path and os.path.exists(executable_path):
                exe_sha256, exe_md5 = await self._compute_hashes(executable_path)

            is_signed = False
            signer_name = None
            if executable_path and os.path.exists(executable_path):
                is_signed, signer_name = await self._check_signature(executable_path)

            # Determine if task runs with highest privileges
            run_as_admin = row.get("Run With Highest Privileges", "").lower() == "true"

            record = StartupTelemetry(
                agent_id=self.config.agent.id if self.config and self.config.agent.id else "unknown",
                collected_at=datetime.now(timezone.utc),
                sequence=0,
                source=StartupSource.SCHEDULED_TASK,
                source_key=task_name,
                name=task_name,
                command=executable_path,
                arguments=arguments,
                user_context=row.get("UserName", ""),
                run_as_admin=run_as_admin,
                executable_path=executable_path,
                working_directory=row.get("Start In", "") or None,
                exe_sha256=exe_sha256,
                exe_md5=exe_md5,
                is_signed=is_signed,
                signer_name=signer_name,
                enabled=row.get("Status", "").lower() == "ready",
                task_triggers=row.get("Trigger", ""),
                task_actions=f"{executable_path} {arguments}" if arguments else executable_path,
                task_conditions=row.get("Conditions", ""),
                task_settings=row.get("Settings", ""),
                is_complete=True,
            )

            return record
        except Exception as e:
            self.logger.debug(
                "task_record_creation_failed",
                task=row.get("TaskName", ""),
                error=str(e),
            )
            return None

    async def _collect_wmi_subscriptions(
        self,
    ) -> Tuple[List[StartupTelemetry], List[CollectionError]]:
        """Collect WMI event subscriptions."""
        records: List[StartupTelemetry] = []
        errors: List[CollectionError] = []

        try:
            import wmi

            c = await asyncio.to_thread(wmi.WMI)

            # Get event filters
            for filter_obj in await asyncio.to_thread(c.__getattribute__, "Win32_NTEventLogEvent"):
                pass  # This is just a placeholder - WMI queries need specific queries

            # Query for event consumers
            consumers = await asyncio.to_thread(
                lambda: list(c.query("SELECT * FROM __EventConsumer"))
            )

            for consumer in consumers:
                try:
                    with LogContext(consumer_name=consumer.Name):
                        record = await self._create_wmi_record(consumer)
                        if record:
                            records.append(record)
                except Exception as e:
                    self.logger.debug(
                        "wmi_consumer_record_failed",
                        consumer=consumer.Name,
                        error=str(e),
                    )

        except ImportError:
            # wmi module not available
            self.logger.debug("wmi_module_not_available")
        except Exception as e:
            errors.append(CollectionError(
                collector_name=self.name,
                error_type=type(e).__name__,
                error_message=f"WMI subscription collection failed: {e}",
                is_recoverable=True,
            ))

        return records, errors

    async def _create_wmi_record(self, consumer: Any) -> Optional[StartupTelemetry]:
        """Create startup record from WMI event consumer."""
        try:
            record = StartupTelemetry(
                agent_id=self.config.agent.id if self.config and self.config.agent.id else "unknown",
                collected_at=datetime.now(timezone.utc),
                sequence=0,
                source=StartupSource.WMI_SUBSCRIPTION,
                source_key=getattr(consumer, "Name", "unknown"),
                name=getattr(consumer, "Name", "unknown"),
                command=getattr(consumer, "CommandLineTemplate", None),
                executable_path=getattr(consumer, "ExecutablePath", None),
                is_complete=True,
            )
            return record
        except Exception as e:
            self.logger.debug("wmi_record_failed", error=str(e))
            return None

    async def _detect_changes(self, current_entries: Dict[str, Dict[str, Any]]) -> None:
        """Detect changes in startup entries."""
        previous_keys = set(self._previous_entries.keys())
        current_keys = set(current_entries.keys())

        new_entries = current_keys - previous_keys
        removed_entries = previous_keys - current_keys

        for key in new_entries:
            entry = current_entries[key]
            self.logger.warning(
                "new_startup_entry_detected",
                source=entry.get("source"),
                name=entry.get("name"),
                command=entry.get("command"),
            )

        for key in removed_entries:
            entry = self._previous_entries[key]
            self.logger.warning(
                "startup_entry_removed",
                source=entry.get("source"),
                name=entry.get("name"),
            )

    async def _compute_hashes(self, file_path: str) -> Tuple[Optional[str], Optional[str]]:
        """Compute SHA-256 and MD5 hashes for a file."""
        try:
            loop = asyncio.get_event_loop()

            def compute():
                sha256_hash = hashlib.sha256()
                md5_hash = hashlib.md5()

                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        sha256_hash.update(chunk)
                        md5_hash.update(chunk)

                return sha256_hash.hexdigest(), md5_hash.hexdigest()

            return await loop.run_in_executor(None, compute)
        except Exception:
            return None, None

    async def _check_signature(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """Check if file has a valid digital signature."""
        try:
            # Placeholder for signature verification
            return False, None
        except Exception:
            return False, None
