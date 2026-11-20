"""
SentinelWatch Agent - Main Entry Point.

The Windows endpoint monitoring agent that collects telemetry
and sends it to the backend API.
"""

import argparse
import asyncio
import signal
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import AgentConfig, get_config, merge_collection_config, set_config
from .health import HealthMonitor, get_system_info, CollectorStatus
from .logging import get_logger, log_shutdown, log_startup, setup_logging
from .models import AgentHealth
from .collectors import (
    ProcessCollector,
    ServiceCollector,
    StartupCollector,
    EventLogCollector,
)
from .transport import (
    HTTPClient,
    HTTPClientConfig,
    MultiTelemetryBatcher,
)
from .crypto.certificates import (
    generate_key_pair,
    create_csr,
    csr_to_pem,
    private_key_to_pem,
)
from .identity import EndpointIdentity, create_identity_manager


logger = get_logger(__name__)


class SentinelWatchAgent:
    """Main agent application."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.health_monitor = HealthMonitor(config)
        self.agent_health = AgentHealth(
            agent_id=config.agent.id or "unknown",
            version="0.1.0",
        )
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._collector_tasks: list[asyncio.Task] = []
        self._config_version = 0
        self._config_poll_event = asyncio.Event()

        # Initialize identity manager
        data_dir = config.get_data_dir()
        self.identity_manager = create_identity_manager(data_dir)

        # Initialize collectors
        self._collectors = {}
        self._multi_batcher: Optional[MultiTelemetryBatcher] = None
        self._http_client: Optional[HTTPClient] = None

    async def initialize(self) -> None:
        """Initialize agent components."""
        logger.info("agent_initializing", version="0.1.0")

        # Load or create endpoint identity
        enrollment_token = self.config.agent.enrollment_token
        identity = self.identity_manager.get_or_create_identity(enrollment_token)

        # Update config with stored agent_id if available
        if identity.get("agent_id"):
            self.config.agent.id = identity["agent_id"]
            # Also update private key for mTLS
            if identity.get("private_key_pem"):
                self.config.agent.private_key_pem = identity["private_key_pem"]

        # Initialize HTTP client
        http_config = HTTPClientConfig.from_agent_config(self.config)
        self._http_client = HTTPClient(http_config)

        # Check/perform agent registration
        await self._ensure_agent_registered()
        if not self.config.agent.id or not self._http_client.has_agent_credentials:
            raise RuntimeError(
                "Agent enrollment is incomplete. Configure a valid enrollment token or restore a valid enrolled identity."
            )

        # Initialize multi-batcher
        self._multi_batcher = MultiTelemetryBatcher(
            agent_id=self.config.agent.id or "unknown",
            config=self.config,
        )
        await self._multi_batcher.start()

        # Initialize collectors
        self._collectors = {
            "process": ProcessCollector(self.config),
            "service": ServiceCollector(self.config),
            "startup": StartupCollector(self.config),
            "eventlog": EventLogCollector(self.config),
        }

        # Start collectors
        for name, collector in self._collectors.items():
            # Register collector with health monitor
            self.health_monitor.register_collector(name)
            self.agent_health.collectors[name] = collector.get_stats()

            # Start collector with callback to batcher
            self._collector_tasks.append(
                asyncio.create_task(self._run_collector(name, collector))
            )

        logger.info("agent_initialized", collectors=list(self._collectors.keys()))

    async def _ensure_agent_registered(self) -> None:
        """Enroll (or refresh credentials for) this machine when configured."""
        if not self.config.agent.enrollment_token:
            identity = self.identity_manager.load()
            if self._activate_stored_credentials(identity):
                return
            logger.warning("agent_not_configured", message="Enrollment token missing")
            return

        # Check if re-enrollment is needed
        needs_re_enroll, reason = self.identity_manager.needs_re_enrollment()
        if needs_re_enroll:
            logger.info("re_enrollment_required", reason=reason)
            # Reset identity to trigger fresh registration
            self.identity_manager.reset_identity()
            # Create new identity
            identity = self.identity_manager.get_or_create_identity(self.config.agent.enrollment_token)
            if identity.get("private_key_pem"):
                self.config.agent.private_key_pem = identity["private_key_pem"]

        await self._register_agent()

    def _activate_stored_credentials(self, identity: Optional[dict]) -> bool:
        """Restore a previously enrolled endpoint without retaining its one-time token."""
        if not identity or not identity.get("agent_id"):
            return False
        access_token = identity.get("agent_token")
        refresh_token = identity.get("agent_refresh_token")
        if not access_token or not refresh_token or not self._http_client:
            return False

        agent_id = identity["agent_id"]
        self.config.agent.id = agent_id
        if identity.get("private_key_pem"):
            self.config.agent.private_key_pem = identity["private_key_pem"]
        self._http_client.set_agent_credentials(
            access_token,
            refresh_token,
            lambda access, refresh: self.identity_manager.update_agent_token(agent_id, access, refresh),
        )
        return True

    async def _register_agent(self) -> None:
        """Register agent with backend and store certificate."""
        try:
            # Get or create identity
            identity = self.identity_manager.get_or_create_identity(self.config.agent.enrollment_token)

            # If already registered, check if we need to re-register
            if identity.get("agent_id") and not identity.get("needs_re_enrollment"):
                logger.info("agent_already_registered", agent_id=identity["agent_id"])
                if self._activate_stored_credentials(identity):
                    return
                logger.warning("agent_credential_missing", action="rotating_with_enrollment_token")

            # Generate key pair if not present
            private_key_pem = identity.get("private_key_pem")
            if not private_key_pem:
                private_key = generate_key_pair()
                private_key_pem = private_key_to_pem(private_key)
                identity["private_key_pem"] = private_key_pem

            # Create CSR
            csr = create_csr(private_key_pem)
            csr_pem = csr_to_pem(csr)

            # Get system info
            import platform
            machine_guid = self._get_machine_guid()
            hostname = platform.node()
            os_version = f"{platform.system()} {platform.release()} {platform.version()}"

            # Register with backend
            if self._http_client:
                response, error = await self._http_client.register_agent(
                    enrollment_token=self.config.agent.enrollment_token,
                    machine_guid=machine_guid,
                    hostname=hostname,
                    os_version=os_version,
                    agent_version="0.1.0",
                    csr_pem=csr_pem,
                )

                if error:
                    logger.error("agent_registration_failed", error=error.error_message)
                    return

                if response:
                    agent_id = response.get("agent_id")
                    agent_token = response.get("agent_token")
                    agent_refresh_token = response.get("agent_refresh_token")
                    if not agent_id or not agent_token or not agent_refresh_token:
                        logger.error("agent_registration_failed", error="Backend response omitted agent credentials")
                        return

                    # Update identity with new agent_id
                    if not self.identity_manager.update_agent_token(agent_id, agent_token, agent_refresh_token):
                        logger.error("agent_credential_persistence_failed", agent_id=agent_id)
                        return

                    # Update config
                    self.config.agent.id = agent_id
                    self._http_client.set_agent_credentials(
                        agent_token,
                        agent_refresh_token,
                        lambda access, refresh: self.identity_manager.update_agent_token(agent_id, access, refresh),
                    )
                    self._apply_server_config(
                        response.get("config"), response.get("config_version")
                    )
                    logger.info("agent_registered", agent_id=agent_id)
                    if response.get("config_version"):
                        logger.info("agent_config_received", version=response["config_version"])

        except Exception as e:
            logger.error("agent_registration_failed", error=str(e))

    def _get_machine_guid(self) -> str:
        """Get Windows machine GUID."""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            )
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            return guid
        except Exception:
            return "unknown"

    async def _run_collector(self, name: str, collector) -> None:
        """Run a collector and forward records to batcher."""
        try:
            await collector.run_continuous(
                callback=lambda result: self._on_collector_result(name, result)
            )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("collector_task_failed", collector=name, error=str(e))

    async def _on_collector_result(self, collector_name: str, result) -> None:
        """Handle collection result from a collector."""
        # Update health stats
        collector_stats = self.agent_health.get_collector(collector_name)
        self.agent_health.collectors[collector_name] = collector_stats

        # Forward records to batcher
        if self._multi_batcher and result.records:
            for record in result.records:
                await self._multi_batcher.add_record(collector_name, record)

        # Log collection summary
        if result.record_count > 0 or result.errors:
            logger.info(
                "collection_complete",
                collector=collector_name,
                records=result.record_count,
                errors=len(result.errors),
                duration_ms=result.duration_ms,
            )

        # Update agent health
        self.agent_health.update_overall_status()

    async def start(self) -> None:
        """Start the agent."""
        logger.info("agent_starting", version="0.1.0")
        self._running = True

        # Log system info
        sys_info = get_system_info()
        logger.info("system_info", **sys_info)

        # Initialize components
        await self.initialize()

        # Register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._signal_handler, sig)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler for all signals
                pass

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._health_collection_loop()),
            asyncio.create_task(self._config_poll_loop()),
            asyncio.create_task(self._flush_loop()),
            asyncio.create_task(self._heartbeat_loop()),
        ]

        logger.info("agent_started", tasks=len(self._tasks))

        # Wait for all tasks
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await asyncio.gather(*self._collector_tasks, return_exceptions=True)
            if self._multi_batcher:
                await self._multi_batcher.stop()
            logger.info("agent_stopped")

    def _signal_handler(self, sig: signal.Signals) -> None:
        """Handle shutdown signals."""
        logger.info("signal_received", signal=sig.name)
        self.stop()

    def stop(self) -> None:
        """Stop the agent gracefully."""
        logger.info("agent_stopping")
        self._running = False

        # Stop collectors
        for collector in self._collectors.values():
            collector.stop()

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

    async def _health_collection_loop(self) -> None:
        """Periodically collect and log health metrics."""
        health_collector = self.health_monitor.register_collector("health")

        while self._running:
            start_time = asyncio.get_event_loop().time()

            try:
                metrics = self.health_monitor.collect()
                logger.info("health_metrics", **metrics.to_dict())

                # Update agent health
                self.agent_health.cpu_percent = metrics.cpu_percent
                self.agent_health.memory_bytes = int(metrics.memory_mb * 1024 * 1024)
                self.agent_health.memory_percent = metrics.memory_percent
                self.agent_health.disk_usage_bytes = int((100 - metrics.disk_free_gb / metrics.disk_total_gb * 100) * 1024 * 1024 * 1024)
                self.agent_health.disk_usage_percent = 100 - metrics.disk_free_gb / metrics.disk_total_gb * 100 if metrics.disk_total_gb > 0 else 0
                self.agent_health.uptime_seconds = metrics.uptime_seconds
                self.agent_health.queue_depth = metrics.queue_depth
                self.agent_health.batches_sent = metrics.batches_sent
                self.agent_health.batches_failed = metrics.batches_failed
                self.agent_health.events_sent = metrics.events_sent
                self.agent_health.events_rejected = metrics.events_rejected
                self.agent_health.last_heartbeat_at = metrics.last_heartbeat
                self.agent_health.last_config_poll_at = metrics.last_config_poll

                # Sync collector stats
                for name, collector in self._collectors.items():
                    stats = collector.get_stats()
                    self.agent_health.collectors[name] = stats

                self.agent_health.update_overall_status()

            except Exception as e:
                logger.error("health_collection_failed", error=str(e))
                health_collector.errors_count += 1
                health_collector.last_error = str(e)
                health_collector.healthy = False
            else:
                health_collector.healthy = True

            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            health_collector.runs_count += 1
            health_collector.last_run = datetime.now(timezone.utc)
            health_collector.avg_duration_ms = (
                (health_collector.avg_duration_ms * (health_collector.runs_count - 1) + duration_ms) / health_collector.runs_count
            )

            try:
                await asyncio.sleep(self.config.collection.health)
            except asyncio.CancelledError:
                break

    async def _config_poll_loop(self) -> None:
        """Periodically poll backend for configuration updates."""
        while self._running:
            try:
                if self._http_client and self.config.agent.id:
                    response, error = await self._http_client.get_agent_config(
                        self.config.agent.id,
                        self._config_version,
                    )

                    if error:
                        logger.warning("config_poll_failed", error=error.error_message)
                    elif response:
                        if response.get("config_update_available"):
                            self._apply_server_config(
                                response.get("config"), response.get("config_version")
                            )
                        self.agent_health.last_config_poll_at = datetime.now(timezone.utc)
                        self.health_monitor.record_config_poll()
                    else:
                        logger.debug("config_poll_no_changes")

            except Exception as e:
                logger.error("config_poll_error", error=str(e))

            try:
                await asyncio.wait_for(
                    self._config_poll_event.wait(),
                    timeout=self.config.collection.config,
                )
                self._config_poll_event.clear()
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    def _apply_server_config(self, config_data, version) -> None:
        """Apply bounded server-supplied collection intervals."""
        if not isinstance(config_data, dict):
            return
        try:
            updated = merge_collection_config(
                self.config.collection,
                config_data.get("collection_intervals", {}),
            )
            new_version = int(version)
            if new_version < 0:
                raise ValueError("config version cannot be negative")
        except (TypeError, ValueError) as exc:
            logger.warning("config_update_rejected", error=str(exc))
            return

        self.config.collection = updated
        self._config_version = new_version
        for collector in self._collectors.values():
            collector.notify_config_changed()
        logger.info(
            "config_update_applied",
            version=new_version,
            collection_intervals=updated.model_dump(),
        )

    async def _flush_loop(self) -> None:
        """Periodically flush telemetry batches to backend."""
        flush_interval = 5.0  # seconds

        while self._running:
            try:
                if self._multi_batcher and self._http_client:
                    batches = await self._multi_batcher.flush_all()

                    for telemetry_type, batch in batches.items():
                        if batch and batch.records:
                            response, error = await self._http_client.send_telemetry_batch(
                                batch,
                                compress=self.config.batching.compress,
                            )

                            if error:
                                logger.error(
                                    "batch_send_failed",
                                    telemetry_type=telemetry_type,
                                    error=error.error_message,
                                    records=len(batch.records),
                                )
                                self.agent_health.batches_failed += 1
                                dropped = await self._multi_batcher.requeue(telemetry_type, batch)
                                if dropped:
                                    self.agent_health.events_rejected += dropped
                                self.agent_health.queue_depth = self._multi_batcher.total_buffered_records()
                            else:
                                logger.info(
                                    "batch_sent",
                                    telemetry_type=telemetry_type,
                                    records=len(batch.records),
                                    accepted=response.get("accepted") if response else None,
                                    rejected=response.get("rejected") if response else None,
                                )
                                self.agent_health.batches_sent += 1
                                self.agent_health.events_sent += (
                                    response.get("accepted", len(batch.records)) if response else len(batch.records)
                                )
                                self.agent_health.events_rejected += (
                                    response.get("rejected", 0) if response else 0
                                )
                                self.agent_health.last_heartbeat_at = datetime.now(timezone.utc)

                    self.agent_health.queue_depth = self._multi_batcher.total_buffered_records()

            except Exception as e:
                logger.error("flush_loop_error", error=str(e))

            try:
                await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                break

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to backend."""
        while self._running:
            try:
                if self._http_client and self.config.agent.id:
                    health_data = {
                        "cpu_percent": self.agent_health.cpu_percent,
                        "memory_mb": self.agent_health.memory_bytes / (1024 * 1024),
                        "memory_percent": self.agent_health.memory_percent,
                        "disk_usage_percent": self.agent_health.disk_usage_percent,
                        "queue_depth": self.agent_health.queue_depth,
                        "config_version": self._config_version,
                        "collectors": {
                            name: stats.model_dump(mode="json")
                            for name, stats in self.agent_health.collectors.items()
                        },
                    }

                    response, error = await self._http_client.send_heartbeat(
                        agent_id=self.config.agent.id,
                        health_data=health_data,
                        version="0.1.0",
                    )

                    if error:
                        logger.warning("heartbeat_failed", error=error.error_message)
                    else:
                        self.agent_health.last_heartbeat_at = datetime.now(timezone.utc)
                        if response and response.get("config_update_available"):
                            self._config_poll_event.set()
                        logger.debug("heartbeat_sent")

            except Exception as e:
                logger.error("heartbeat_error", error=str(e))

            try:
                await asyncio.sleep(self.config.collection.heartbeat)
            except asyncio.CancelledError:
                break


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="sentinelwatch-agent",
        description="SentinelWatch Windows Endpoint Monitoring Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-c", "--config",
        type=Path,
        help="Path to configuration file (default: config/agent.yaml)",
    )

    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate configuration and exit",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Install service command
    install_parser = subparsers.add_parser("install", help="Install as Windows service")
    install_parser.add_argument("--name", help="Service name")

    # Uninstall service command
    subparsers.add_parser("uninstall", help="Uninstall Windows service")

    # Start service command
    subparsers.add_parser("start", help="Start Windows service")

    # Stop service command
    subparsers.add_parser("stop", help="Stop Windows service")

    return parser


async def run_agent(config_path: Optional[Path] = None) -> int:
    """Run the agent with the given configuration."""
    try:
        # Load configuration
        config = AgentConfig.load(config_path)
        set_config(config)

        # Setup logging
        setup_logging(config)
        log_startup(config)

        # Validate configuration
        if config_path:
            logger.info("config_loaded", path=str(config_path))
        else:
            logger.info("config_loaded", path="defaults + environment")

        # Create and start agent
        agent = SentinelWatchAgent(config)
        await agent.start()

        return 0

    except Exception as e:
        logger.error("agent_failed", error=str(e))
        return 1
    finally:
        log_shutdown()


def main() -> int:
    """Main entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()

    # Handle config validation
    if args.validate_config:
        try:
            config = AgentConfig.load(args.config)
            print("Configuration valid!")
            print(f"Backend URL: {config.backend.url}")
            print(f"Collection intervals: {config.collection.model_dump()}")
            return 0
        except Exception as e:
            print(f"Configuration invalid: {e}", file=sys.stderr)
            return 1

    # Handle service commands
    if args.command in ("install", "uninstall", "start", "stop"):
        try:
            config = AgentConfig.load(args.config)
            from .windows_service import run_service_command

            return run_service_command(
                args.command,
                config,
                args.config,
                getattr(args, "name", None),
            )
        except Exception as e:
            print(f"Windows service command failed: {e}", file=sys.stderr)
            return 1

    # Run agent
    return asyncio.run(run_agent(args.config))


if __name__ == "__main__":
    sys.exit(main())
