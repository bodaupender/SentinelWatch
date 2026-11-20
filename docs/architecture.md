# SentinelWatch Architecture

## Overview
SentinelWatch is a professional Windows endpoint process and service monitoring platform with an enterprise-style SOC dashboard. It consists of three main components:

1. **Windows Agent** - Runs on endpoints, collects telemetry
2. **Backend API** - Receives, processes, stores telemetry; runs detection engine
3. **SOC Dashboard** - React-based frontend for analysts

## Component Architecture

### Windows Agent (`agent/`)
- **Process Telemetry Collector** - Enumerates running processes via `psutil`, captures PID, PPID, command line, executable path, hashes, user context, network connections
- **Windows Service Collector** - Enumerates services via `pywin32`/`wmi`, captures service name, display name, status, start type, binary path, dependencies
- **Startup Inventory Collector** - Reads registry Run keys, scheduled tasks, startup folder
- **Windows Event Log Collector** - Subscribes to Security, System, Application logs for relevant events (4688, 7045, etc.)
- **Telemetry Sender** - Batches and sends data to the backend using per-agent bearer credentials; use HTTPS for remote deployments
- **Configuration Client** - Polls backend for config updates (collection intervals, rule sets)
- **Self-Health Monitor** - Reports agent health, resource usage, version

### Backend API (`backend/`)
- **FastAPI Application** - RESTful API with OpenAPI docs
- **Telemetry Ingestion Endpoints** - Receive process, service, startup, event log data
- **Detection Engine** - Evaluates rules against incoming telemetry in real-time
- **Alert Management** - Creates, enriches, deduplicates, correlates alerts
- **Evidence Storage** - Stores raw telemetry snapshots linked to alerts
- **Agent Management** - Registration, heartbeat, config distribution, command & control
- **Authentication & Authorization** - JWT-based auth, RBAC for analysts
- **Audit Logging** - Immutable audit trail of all admin actions
- **Database Layer** - SQLAlchemy ORM with Alembic migrations
  - Development: SQLite
  - Production: PostgreSQL

### SOC Dashboard (`frontend/`)
- **Agent Inventory** - Live view of registered endpoints
- **Process Explorer** - Searchable, filterable process table with details
- **Service Monitor** - Service state across endpoints
- **Alert Console** - Triaging interface with severity, timeline, evidence
- **Detection Rules Manager** - View, test, enable/disable rules
- **Audit Log Viewer** - Searchable audit trail
- **Settings** - Agent config, user management, integration config

### Detection Rules (`detection-rules/`)
- **YARA-L-inspired DSL** - Rule format for process/service/event patterns
- **Rule Categories**:
  - Process anomalies (living-off-the-land, suspicious parents, masquerading)
  - Service anomalies (new services, modified binaries, suspicious paths)
  - Startup persistence (new Run keys, scheduled tasks, WMI subscriptions)
  - Event log signatures (4688 with suspicious args, 7045 service installs)
  - MITRE ATT&CK mapping

## Data Flow

```
[Endpoint]                    [Backend]                      [Dashboard]
   │                            │                               │
   ├─ Agent starts              │                               │
   ├─ Registers ───────────────►│                               │
   │                            ├─ Creates agent record        │
   │                            │◄── Returns config, rules ────┤
   ├─ Collects telemetry        │                               │
   ├─ Sends batches ───────────►│                               │
   │                            ├─ Stores raw telemetry        │
   │                            ├─ Runs detection engine       │
   │                            ├─ Creates alerts              │
   │                            │◄── Tenant SSE invalidation ──┤
   │                            │                               │
   ├─ Heartbeat ───────────────►│                               │
   │◄── Config updates ─────────┤                               │
```

## Technology Stack

| Layer | Technology |
|-------|------------|
| Agent Language | Python 3.12+ |
| Agent Libraries | psutil, pywin32, requests, pydantic, pyyaml |
| Backend Framework | FastAPI |
| Backend Validation | Pydantic v2 |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Dev Database | SQLite |
| Prod Database | PostgreSQL |
| Frontend Framework | React 18 + TypeScript |
| Build Tool | Vite |
| Styling | Tailwind CSS |
| UI Components | shadcn/ui |
| Icons | Lucide React |
| Charts | Recharts |
| Tables | TanStack Table |
| Testing (Python) | pytest, pytest-asyncio, pytest-cov |
| Testing (Frontend) | Vitest, React Testing Library |
| Packaging | PyInstaller |

## Security Design Principles

1. **Least Privilege** - Agent runs as standard user, only reads system info
2. **Read-Only Monitoring** - No process injection, no kernel drivers, no system modification
3. **Secure Communication** - HTTPS transport with per-agent, revocable bearer credentials. Client-certificate mTLS is not implemented in the current enrollment flow.
4. **Input Validation** - All telemetry validated via Pydantic models
5. **Secret Management** - Certificates/keys via OS cert store or env vars, never in code
6. **Data Minimization** - Collect only what's needed for detection
7. **Audit Trail** - All admin actions logged immutably
8. **Safe Error Handling** - No stack traces to clients, structured error codes
