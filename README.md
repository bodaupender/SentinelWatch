# SentinelWatch

**Professional Windows Endpoint Process and Service Monitoring Platform with Enterprise-Style SOC Dashboard**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-blue.svg)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5+-blue.svg)](https://typescriptlang.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

SentinelWatch is a comprehensive Windows endpoint monitoring platform designed for security operations centers (SOCs). It consists of three main components:

1. **Windows Agent** - Lightweight monitoring agent that collects process, service, startup, and event log telemetry
2. **Backend API** - FastAPI-based REST API with detection engine, alert management, and agent orchestration
3. **SOC Dashboard** - React/TypeScript frontend for alert triage, investigation, and threat hunting

## Architecture

```
┌─────────────┐  HTTPS + token ┌──────────────┐    HTTPS/SSE       ┌─────────────────┐
│   AGENT     │ ◄────────────► │   BACKEND    │ ◄────────────────► │   FRONTEND      │
│  (Endpoint) │                │   (API/DB)   │                    │   (SOC Dash)    │
└─────────────┘                └──────────────┘                    └─────────────────┘
```

## Features

### Agent Capabilities
- **Process Telemetry** - PID, PPID, command line, executable path, hashes, user context, network connections
- **Service Monitoring** - Service name, display name, state, start type, process ID when available, binary path and service account
- **Startup Inventory** - Registry Run keys, scheduled tasks, startup folders, WMI subscriptions
- **Event Log Collection** - Configured Windows event log channels are polled for selected security-relevant events
- **Agent Authentication** - Unique short-lived access tokens and rotating refresh credentials per endpoint; use HTTPS for remote deployments
- **Configurable Collection** - Adjustable intervals, batching, compression
- **Secret Redaction** - Automatic redaction of secrets from command lines
- **Health Monitoring** - Self-reporting CPU, memory, disk, queue metrics

### Backend Capabilities
- **RESTful API** - OpenAPI/Swagger documentation
- **Detection Engine** - CEL-like rule evaluation with MITRE ATT&CK mapping
- **Alert Management** - Triage workflow (new → investigating → resolved)
- **Evidence Storage** - Raw telemetry snapshots linked to alerts
- **Agent Management** - Registration, heartbeat, configuration distribution
- **Authentication** - JWT with refresh tokens, Argon2id password hashing, MFA (TOTP); config signing via HMAC-SHA256 so agents verify integrity
- **Alert Deduplication** - Entity-aware stable keys prevent cross-process suppression; correlation IDs link related alerts to the same telemetry batch
- **Evidence Traceability** - Every alert stores raw telemetry JSONB linked by FK for full investigation chain
- **Audit Logging** - Administrative action history
- **Live Dashboard Refresh** - Tenant-scoped SSE invalidation notices with reconnect and REST polling fallback
- **Prometheus Metrics** - Observability endpoints

### Dashboard Capabilities
- **Agent Inventory** - Live view of registered endpoints with health status
- **Process Explorer** - Searchable, filterable process table across all agents
- **Service Monitor** - Cross-agent service state monitoring
- **Alert Console** - Triage interface with severity, timeline, evidence
- **Detection Rules Manager** - View, test, enable/disable rules with MITRE mapping
- **Audit Log Viewer** - Searchable administrative audit trail
- **Settings** - User management, agent config, theme, notifications
- **Dark/Light Mode** - Full theme support
- **Responsive Design** - Desktop and tablet optimized

## Quick Start

### One-command Windows setup

Prerequisites: Windows 10/11, Python 3.12, and Node.js 20. Extract the SentinelWatch release ZIP, open PowerShell in the extracted folder, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer creates isolated Python environments for the backend and Windows agent, installs the dashboard dependencies, creates a strong local JWT signing key in the ignored `.env` file, and starts the backend and dashboard on `127.0.0.1`. The launcher also starts the endpoint agent on this PC and provisions a random enrollment token in `.env`; collected telemetry is sent only to this PC's local backend. The dashboard opens at http://127.0.0.1:3000; the backend health check is at http://127.0.0.1:8001/health. In this local development setup, use the dashboard registration page to create the first organization owner. Public self-registration is disabled when backend debug mode is off.

### Create the first owner in a production configuration

After installing the backend and applying database migrations, create the initial owner from the server's local console. This command prompts for the password without echoing it, refuses to run once any user exists, and attaches the owner to the existing active organization when one is already present:

```powershell
Push-Location .\backend
try {
    .\.venv\Scripts\python.exe -m alembic upgrade head
    .\.venv\Scripts\sentinelwatch-backend.exe create-owner
} finally {
    Pop-Location
}
```

The browser registration endpoint remains disabled outside debug mode. Run the bootstrap command on the server with access to its configured database; do not share the password or put it in a command argument.

Stop the local agent, backend, and dashboard with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop.ps1
```

For additional endpoints, install the agent separately on each endpoint and configure its backend URL and enrollment credentials before it sends telemetry.

The dashboard's **Enrolled Endpoints** count includes endpoints with a current, non-revoked agent credential generation. Metadata-only inventory entries are tracked separately as unregistered; they do not report process or service telemetry until the Windows agent completes enrollment.

### AI alert investigation (local Ollama)

The **AI Investigation** workspace is available from the dashboard navigation and from each alert's investigation page. It correlates alert evidence with process, service, and Windows event telemetry collected from the same endpoint within 30 minutes of the alert. Reports are advisory and read-only; analysts decide whether to take any recommended action.

Install and start Ollama separately, then download the default model:

```powershell
ollama pull qwen3.5:4b
```

The backend uses `http://127.0.0.1:11434` and `qwen3.5:4b` by default. Override these in the ignored `.env` file with `SW_BACKEND_AI__OLLAMA_URL` and `SW_BACKEND_AI__MODEL`. Use `SW_BACKEND_AI__PROVIDER=ollama`; the current build supports local Ollama only. If Ollama or the model is unavailable, the dashboard shows an explicit error and the rest of the alert workflow remains available.

### Manual development setup

From the project root, install dependencies and generate the local signing key with:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -SkipStart
```

Then start the services with `scripts\start.ps1` and stop them with `scripts\stop.ps1`.
### GitHub releases

Pushing a version tag such as `v1.0.0` runs the Windows release workflow. It checks the backend tests and frontend build, then attaches a clean `SentinelWatch-v1.0.0-windows.zip` source bundle to the GitHub Release. Download and extract that bundle before running the installer above. The bundle does not contain `.env` secrets, local databases, virtual environments, or installed dependencies.

## Project Structure

```
SentinelWatch/
├── agent/                 # Windows monitoring agent
│   ├── src/sentinelwatch_agent/
│   ├── config/
│   └── tests/
├── backend/               # FastAPI backend
│   ├── src/sentinelwatch_backend/
│   ├── alembic/           # Database migrations
│   ├── config/
│   └── tests/
├── frontend/              # React/TypeScript dashboard
│   ├── src/
│   ├── public/
│   └── tests/
├── detection_rules/       # Detection rules
├── config/                # Shared configuration examples
├── docs/                  # Documentation
│   ├── architecture.md
│   ├── threat-model.md
│   ├── security-design.md
│   ├── data-flow.md
│   └── development-plan.md
├── scripts/               # Development scripts
└── tests/                 # Integration tests
```

## Security

SentinelWatch follows defensive security principles:

- **Least Privilege** - Agent uses read-only collection; run it with only the permissions needed for enabled collectors
- **Agent Authentication** - Per-agent bearer tokens over TLS; mTLS client-certificate authentication is not implemented
- **Input Validation** - Strict Pydantic validation on all telemetry
- **Secret Redaction** - Automatic redaction of credentials from command lines
- **Audit Trail** - Immutable logging of all administrative actions
- **RBAC** - Role-based access control (admin, analyst, viewer)
- **MFA** - TOTP support for administrative accounts

See [docs/security-design.md](docs/security-design.md) and [docs/threat-model.md](docs/threat-model.md) for details. Process command lines and usernames can contain sensitive data; review the collection and redaction settings before deployment.

## Documentation

- [Architecture](docs/architecture.md) - System architecture and component design
- [Threat Model](docs/threat-model.md) - Threat modeling and risk assessment
- [Security Design](docs/security-design.md) - Security implementation details
- [Data Flow](docs/data-flow.md) - Detailed data flow diagrams
- [Development Plan](docs/development-plan.md) - Phase-by-phase implementation plan
- [Acceptance Matrix](docs/acceptance-matrix.md) - Current implementation and verification status

## Development Phases

Status distinguishes implementation from verification: a component may be implemented while tests or hardening remain outstanding.

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 1** | ✅ Complete | Architecture, security design, and project foundation |
| Phase 2 | ✅ Implemented | Windows monitoring agent; the completion report marks this phase complete. The recorded baseline still shows 2 agent test failures. |
| Phase 3 | 🟡 Implemented; verification needed | Backend API and detection engine are present. See the technical debt and audit documents for known issues that need confirmation against the current code. |
| Phase 4 | 🟡 Implemented; verification needed | SOC dashboard is present. The recorded baseline build passed, but it found no frontend unit tests. |
| Phase 5 | 🟡 Partially implemented | Detection rules and tests are present; 2 agent tests failed in the recorded baseline, and Bandit was not run. |
| Phase 6 | 🟡 In progress | Installer and release workflow are present; final hardening and security verification remain. |

The verification notes above come from the recorded baseline report dated 2026-11-14, not a fresh test run. See the [baseline test report](BASELINE_TEST_REPORT.md), [feature implementation matrix](FEATURE_IMPLEMENTATION_MATRIX.md), [technical debt register](TECHNICAL_DEBT.md), and [security review](FINAL_SECURITY_REVIEW.md) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

For issues and questions, please use the GitHub issue tracker.
