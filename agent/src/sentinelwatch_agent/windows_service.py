"""Windows Service Control Manager host for the SentinelWatch agent."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import win32service
import win32serviceutil

from .config import AgentConfig, set_config
from .logging import log_shutdown, log_startup, setup_logging


class SentinelWatchWindowsService(win32serviceutil.ServiceFramework):
    """Run one SentinelWatch agent instance under the Windows Service Manager."""

    _svc_name_ = "SentinelWatchAgent"
    _svc_display_name_ = "SentinelWatch Monitoring Agent"
    _svc_description_ = "Collects and uploads authorized Windows endpoint telemetry."

    def __init__(self, args):
        super().__init__(args)
        self._service_name = args[0]
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_requested: asyncio.Event | None = None

    def SvcStop(self):  # noqa: N802 - pywin32 callback name
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self._loop and self._stop_requested:
            self._loop.call_soon_threadsafe(self._stop_requested.set)

    def SvcDoRun(self):  # noqa: N802 - pywin32 callback name
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_agent())
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.close()
            self._loop = None
            log_shutdown()

    async def _run_agent(self) -> None:
        config_path = win32serviceutil.GetServiceCustomOption(
            self._service_name, "config_path", ""
        )
        working_directory = win32serviceutil.GetServiceCustomOption(
            self._service_name, "working_directory", ""
        )
        if working_directory and Path(working_directory).is_dir():
            os.chdir(working_directory)

        config = AgentConfig.load(Path(config_path) if config_path else None)
        set_config(config)
        setup_logging(config)
        log_startup(config)
        self._stop_requested = asyncio.Event()
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)

        from .main import SentinelWatchAgent

        agent = SentinelWatchAgent(config)
        agent_task = asyncio.create_task(agent.start(), name="sentinelwatch-agent")
        stop_task = asyncio.create_task(self._stop_requested.wait(), name="service-stop")
        done, _ = await asyncio.wait(
            {agent_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done:
            agent.stop()
            await agent_task
        else:
            stop_task.cancel()
            await agent_task
            raise RuntimeError("Agent main loop exited before the service was stopped.")


def _configure_recovery(service_name: str) -> None:
    """Ask SCM to restart the service after an unexpected failure."""
    manager = win32service.OpenSCManager(
        None, None, win32service.SC_MANAGER_CONNECT
    )
    try:
        service = win32service.OpenService(
            manager,
            service_name,
            win32service.SERVICE_CHANGE_CONFIG,
        )
        try:
            win32service.ChangeServiceConfig2(
                service,
                win32service.SERVICE_CONFIG_FAILURE_ACTIONS,
                {
                    "ResetPeriod": 86400,
                    "RebootMsg": None,
                    "Command": None,
                    "Actions": [
                        (win32service.SC_ACTION_RESTART, 5000),
                        (win32service.SC_ACTION_RESTART, 15000),
                        (win32service.SC_ACTION_RESTART, 60000),
                    ],
                },
            )
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(manager)


def run_service_command(
    command: str,
    config: AgentConfig,
    config_path: Path | None = None,
    service_name: str | None = None,
) -> int:
    """Install, remove, start, or stop the configured Windows service."""
    name = service_name or config.service_install.name
    if not name or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for character in name):
        raise ValueError("Service name may contain only letters, numbers, dot, dash, and underscore.")

    service_class = SentinelWatchWindowsService
    service_class._svc_name_ = name
    service_class._svc_display_name_ = config.service_install.display_name
    service_class._svc_description_ = config.service_install.description

    argv = [sys.argv[0], command]
    if command == "install":
        argv.extend(["--startup", config.service_install.start_type])
        account = config.service_install.account.strip().lower()
        if account in {"localservice", "nt authority\\localservice"}:
            argv.extend(["--username", "NT AUTHORITY\\LocalService"])
        elif account in {"networkservice", "nt authority\\networkservice"}:
            argv.extend(["--username", "NT AUTHORITY\\NetworkService"])
        elif account not in {"localsystem", "system"}:
            raise ValueError(
                "Service account must be LocalSystem, LocalService, or NetworkService."
            )

        resolved_config = str(config_path.resolve()) if config_path else ""
        working_directory = str(Path.cwd().resolve())

        def persist_service_options(*_options) -> None:
            win32serviceutil.SetServiceCustomOption(name, "config_path", resolved_config)
            win32serviceutil.SetServiceCustomOption(name, "working_directory", working_directory)
            _configure_recovery(name)

        return win32serviceutil.HandleCommandLine(
            service_class,
            argv=argv,
            customOptionHandler=persist_service_options,
        )

    return win32serviceutil.HandleCommandLine(service_class, argv=argv)
