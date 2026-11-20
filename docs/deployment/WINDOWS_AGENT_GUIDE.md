# SentinelWatch Windows Agent Installation Guide

**Version:** 1.0
**Date:** 2026-11-12

---

## Overview

The SentinelWatch Windows Agent is a defensive monitoring agent that collects telemetry from Windows endpoints and sends it to the SentinelWatch backend for security analysis. Collection is read-only with respect to monitored process and service state; the agent does write local identity, queue, bookmark and log files, and service installation changes Windows Service Control Manager configuration. It does not provide remote response actions.

---

## Supported Windows Versions

Windows 10 and Windows 11 are the implementation targets. This worktree has not been runtime-validated on either OS version. Windows Server compatibility is also **not tested**; do not treat earlier claims of full Server support as acceptance evidence.

The agent requires Python 3.12 or later for the source installation path. The current repository does not provide a signed standalone installer or prebuilt agent binary.

## Runtime and permissions

The repository's service command installs `SentinelWatchAgent` with automatic startup and restart recovery. Its default account is LocalSystem. That account has broad machine privileges; a least-privilege service account is not configured automatically. The installer supports the built-in LocalService and NetworkService accounts, but their collector access must be validated on the target Windows version.

The agent reads process and service metadata and selected Windows Event Log channels. Access-denied results are reported as collection errors; missing values are not filled with invented data. Protect the agent configuration file because it contains the enrollment token. The agent stores its enrolled identity using Windows DPAPI for the account that runs it. Run the service and agent under one consistent account and do not run a second copy of the agent against the same identity directory.

## Install and run the agent service

On each endpoint, extract or clone the project, then open an elevated PowerShell window in the project folder. Create the agent environment and configuration:

```powershell
Push-Location .\agent
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .\config\agent.yaml.example .\config\agent.yaml
```

Edit `agent\config\agent.yaml` to set `backend.url` to the central server's HTTPS URL and `agent.enrollment_token` to a token generated for the intended organization. Keep `data_dir` on a local disk. Restrict the config file to Administrators and SYSTEM before installation; do not put the token in a command argument or commit the populated config. Enrollment uses the token only once: after the agent receives its endpoint credentials, it removes the token from its protected identity and keeps only a one-way token marker for restart detection. You may clear `agent.enrollment_token` from the config after successful enrollment; the agent will keep using its saved credentials. To re-enroll, supply a newly generated token.

Install and start the service while still in the `agent` folder:

```powershell
.\.venv\Scripts\sentinelwatch-agent.exe --config .\config\agent.yaml install
.\.venv\Scripts\sentinelwatch-agent.exe --config .\config\agent.yaml start
Get-Service SentinelWatchAgent
```

Check `agent\data\logs\agent.log` for enrollment and collection results. The dashboard should show this endpoint after the first successful heartbeat and process/service uploads. Monitoring continues when the browser closes, as long as the service and server remain available.

Stop or remove the service registration with:

```powershell
.\.venv\Scripts\sentinelwatch-agent.exe --config .\config\agent.yaml stop
.\.venv\Scripts\sentinelwatch-agent.exe --config .\config\agent.yaml remove
```

Service installation and recovery have code paths but have not been exercised against the Windows Service Control Manager in this environment. Validate them on a supported Windows test machine before production use.

---

## Configuration

Use `agent/config/agent.yaml.example` as the template. It is JSON-formatted YAML and uses nested keys. The agent loads the explicitly supplied `--config` path; without it, it checks `config/agent.yaml`, `../config/agent.yaml`, then `/etc/sentinelwatch/agent.yaml` relative to its working directory.

Set these fields before first run:

```yaml
backend:
  url: "https://your-sentinelwatch-server.example"
  api_prefix: "/api/v1"
agent:
  enrollment_token: "<token generated for the intended organization>"
  tags: "optional,comma,separated,tags"
data_dir: "data"
collection:
  process: 5
  service: 30
  heartbeat: 30
```

The checked-in example contains additional sections and safe sample defaults. Do not commit the populated config or expose its enrollment token. Environment overrides use the `SW_AGENT_` prefix and `__` between nested names, for example `SW_AGENT_BACKEND__URL` and `SW_AGENT_AGENT__ENROLLMENT_TOKEN`.

## Backend connection and enrollment

The agent registers at `POST /api/v1/agent/v1/register` using the organization enrollment token, machine GUID, hostname, OS version, agent version and a CSR. The backend returns an agent ID, a 15-minute signed access token, and a rotating 90-day refresh token. The agent keeps both tokens protected with Windows DPAPI and rotates them automatically after an access-token expiry. Refresh-token hashes are stored by the backend; revoking or re-enrolling an agent invalidates its previous credentials. Existing agent identities created before refresh-token support must re-enroll once with a valid enrollment token. The organization enrollment token is needed for first enrollment (or re-enrollment) only, not every service restart.

The current flow does **not** issue or require client certificates and is **not mTLS**. The agent verifies TLS certificates for HTTPS by default; `tls.ca_file` can provide an additional CA bundle. Use HTTPS for any network deployment. The sample hostname is not a usable server address; replace it with the reachable server URL.

Registration and telemetry routes are currently:

- `POST /api/v1/agent/v1/register`
- `POST /api/v1/agent/v1/heartbeat`
- `POST /api/v1/agent/v1/telemetry`
- `POST /api/v1/agent/v1/config/poll`

## Collection and privacy

The example defaults to process collection every 5 seconds, service collection every 30 seconds, heartbeat every 30 seconds, event log every 10 seconds and startup inventory every hour. Values are configurable and bounded by the agent schema. The process collector sends command lines by default (`process.collect_cmdline: true`); turn this off where command-line data is not appropriate. The collector applies configured redaction patterns to collected command lines. Process/service hash collection is disabled in the example because it adds file I/O. Failed telemetry uploads are returned to a bounded in-memory queue, controlled by `batching.max_pending_records` (default 10,000). If that queue fills, the oldest queued records are dropped and the agent logs the count; queued data does not currently survive an agent process or machine restart.

Service inventory is enumerated with `psutil`'s Windows service interface. Fields not exposed by that interface, including some service configuration details, are left unavailable rather than fabricated. Process and service telemetry is uploaded in batches; local buffering and Windows service recovery are present in the code but have not been validated in an SCM runtime test here.

The agent identity file is stored beneath `data_dir` and protects credentials with Windows DPAPI for the account that runs the agent. DPAPI data is account-specific. Choose the service account and data directory before first enrollment. Do not run interactively under one account and then switch the same identity directory to LocalSystem or another account. If a prior identity cannot be decrypted, the agent refuses to replace it; preserve it and investigate instead of deleting it.

## Troubleshooting

| Symptom | Checks |
|---|---|
| Service does not start | Check `Get-Service SentinelWatchAgent`, Windows Application/System event logs, service account and config path. Service Control Manager runtime has not yet been validated by this project. |
| Registration fails | Confirm the enrollment token is valid, unexpired and belongs to the intended organization; verify `backend.url` is reachable and uses HTTPS with a trusted certificate. |
| Dashboard says offline or has no telemetry | Confirm the service is running, the endpoint is enrolled in the expected organization, the backend URL is correct, and the agent log has no authentication or upload errors. Wait for the first heartbeat and telemetry batch. |
| TLS verification fails | Check the server certificate chain and hostname; add the required CA certificate via `tls.ca_file` rather than disabling verification. |
| Process/service fields are missing | Access-denied and unsupported fields may be omitted. Run under an account with the required read permissions and inspect collector health/logs. |
| High CPU or disk activity | Leave hash collection disabled unless needed; reduce the collection frequency only within the supported bounds. |

The default log file is `data/logs/agent.log` relative to `data_dir`. Adjust `logging.file` and `logging.level` in the configuration as needed. To check the service state:

```powershell
Get-Service SentinelWatchAgent
Get-Content .\data\logs\agent.log -Tail 100
```

## Stop, remove, and preserve endpoint data

To stop or remove the SCM registration, run these from the same agent working directory and with the same service name/config used at installation:

```powershell
.\.venv\Scripts\sentinelwatch-agent.exe --config .\config\agent.yaml stop
.\.venv\Scripts\sentinelwatch-agent.exe --config .\config\agent.yaml remove
```

Removing the service registration does not revoke the server-side agent credential and does not erase local identity, queue, bookmark or log files. Revoke the endpoint from the SentinelWatch server when it should no longer report. Preserve `data_dir` unless you have separately decided to dispose of its contents; it contains the endpoint identity and may contain queued telemetry.

## Security and deployment limits

- The configured service account defaults to LocalSystem, which has broad privileges. LocalService and NetworkService are accepted options, but their access requirements have not been validated across Windows versions.
- The project currently uses bearer-token authentication over TLS. It does not provide mTLS, a signed standalone installer, Windows package deployment, or certificate pinning.
- Do not expose the backend over plain HTTP outside an isolated development setup. The current application does not enforce HTTPS at every server entry point.
- Do not treat local logs or telemetry as encrypted at rest based on this guide; storage protection depends on the host and backend database configuration.
- Windows 10/11, service startup/recovery, and install/remove flows require validation on supported Windows test machines before production use. Windows Server support is not tested.

This guide documents the checked-in implementation, not a security or compliance certification.
