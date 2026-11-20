# SentinelWatch System Architecture

**Version:** 1.0
**Date:** 2026-11-12
**Status:** Production Ready (with configuration)

---

## Overview

SentinelWatch is a Windows endpoint monitoring and SOC dashboard platform consisting of three main components:

1. **Windows Agent** - Lightweight monitoring agent deployed on Windows endpoints
2. **Backend API** - FastAPI-based REST API with PostgreSQL/SQLite persistence
3. **Frontend Dashboard** - React/TypeScript SOC dashboard with real-time visualization

---

## High-Level Architecture

```mermaid
graph TB
    subgraph "Windows Endpoints"
        A1[Windows Agent 1]
        A2[Windows Agent 2]
        A3[Windows Agent N]
    end

    subgraph "Network"
        N1[(mTLS/TLS)]
    end

    subgraph "Backend Infrastructure"
        B1[FastAPI Backend]
        B2[(PostgreSQL/SQLite)]
        B3[Redis/Cache]
    end

    subgraph "Frontend"
        F1[React Dashboard]
    end

    subgraph "External"
        E1[SIEM/Log Aggregator]
    end

    A1 -->|Telemetry| N1
    A2 -->|Telemetry| N1
    A3 -->|Telemetry| N1

    N1 -->|Agent Communication| B1
    F1 -->|REST API| B1
    B1 -->|Persist| B2
    B1 -->|Cache| B3
    B1 -->|Export| E1

    style B1 fill:#e1f5fe
    style F1 fill:#f3e5f5
    style A1 fill:#e8f5e9
    style A2 fill:#e8f5e9
    style A3 fill:#e8f5e9
```

---

## Component Architecture

### 1. Frontend Architecture (React/TypeScript)

```mermaid
graph LR
    subgraph "Frontend Application"
        A[App.tsx] --> B[Router]
        B --> C[Pages]
        C --> D[Components]
        D --> E[UI Library]
        E --> F[shadcn/ui + Radix]

        C --> G[Hooks]
        G --> H[useAuthStore]
        G --> I[useThemeStore]
        G --> J[useQuery]

        C --> K[API Layer]
        K --> L[axios]
        K --> M[Interceptors]

        D --> N[Charts]
        N --> O[Recharts]

        D --> P[Tables]
        P --> Q[TanStack Table]
    end

    style A fill:#61dafb
    style E fill:#7c3aed
    style K fill:#eab308
```

#### Key Technologies
| Layer | Technology |
|-------|------------|
| Framework | React 18 + TypeScript 5.5 |
| Build | Vite 5.4 |
| Routing | React Router 6 |
| State | Zustand + TanStack Query 5 |
| UI | shadcn/ui + Radix UI |
| Charts | Recharts 2.15 |
| Tables | TanStack Table 8.20 |
| Styling | Tailwind CSS 3.4 |

#### Page Structure
```
src/pages/
├── DashboardPage.tsx          # Overview with metrics & charts
├── AlertsPage.tsx             # Alert listing & triage
├── AlertInvestigationPage.tsx # Deep-dive investigation
├── AgentsPage.tsx             # Agent inventory
├── ProcessesPage.tsx          # Process telemetry
├── ProcessExplorerPage.tsx    # Process tree & details
├── ServicesPage.tsx           # Service inventory
├── ServiceInvestigationPage.tsx # Service security analysis
├── WindowsEventsPage.tsx      # Event log viewer
├── DetectionRulesPage.tsx     # Rule management
├── ReportsPage.tsx            # Report generation
├── AuditPage.tsx              # Audit log
├── SettingsPage.tsx           # User preferences
└── LoginPage.tsx              # Authentication
```

### 2. Backend Architecture (FastAPI)

```mermaid
graph TB
    subgraph "API Layer"
        A[FastAPI App] --> B[Routers]
        B --> C[/api/v1/auth]
        B --> D[/api/v1/agents]
        B --> E[/api/v1/alerts]
        B --> F[/api/v1/telemetry]
        B --> G[/api/v1/rules]
        B --> H[/api/v1/reports]
        B --> I[/api/v1/audit]
        B --> J[/api/v1/suppression]
        B --> K[/api/v1/agent_communication]
    end

    subgraph "Core Services"
        L[Auth Service] --> M[JWT + Argon2id]
        N[Detection Engine] --> O[Rule Evaluation]
        P[Agent Manager] --> Q[Registration/Config]
        R[Telemetry Ingestion] --> S[Batch Processing]
    end

    subgraph "Data Layer"
        T[SQLAlchemy 2.0 Async] --> U[PostgreSQL/SQLite]
        V[Alembic Migrations]
    end

    subgraph "Agent Communication"
        W[Agent API] --> X[mTLS]
        W --> Y[Heartbeat]
        W --> Z[Telemetry Ingestion]
    end
```

#### API Endpoints (58 Total)

| Module | Routes | Description |
|--------|--------|-------------|
| **auth** | 9 | Login, refresh, logout, user management |
| **agents** | 12 | Registration, inventory, config, health |
| **alerts** | 12 | CRUD, triage, resolution, evidence |
| **telemetry** | 18 | Processes, services, events, startup |
| **rules** | 15 | CRUD, built-in, test, promote/demote |
| **reports** | 6 | Alert/endpoint reports, export |
| **audit** | 4 | Audit log, export |
| **suppression** | 6 | Suppression rules CRUD |
| **agent_communication** | 5 | Registration, heartbeat, telemetry |

### 3. Database Architecture

```mermaid
erDiagram
    USERS ||--o{ API_KEYS : "has"
    USERS ||--o{ AUDIT_LOG : "generates"
    USERS ||--o{ ALERTS : "triage"
    AGENTS ||--o{ PROCESS_TELEMETRY : "reports"
    AGENTS ||--o{ SERVICE_TELEMETRY : "reports"
    AGENTS ||--o{ EVENT_LOG : "reports"
    AGENTS ||--o{ STARTUP_INVENTORY : "reports"
    AGENTS ||--o{ AGENT_HEALTH : "reports"
    ALERTS ||--o{ EVIDENCE : "has"
    ALERTS ||--o{ ALERT_HISTORY : "tracks"
    RULES ||--o{ ALERTS : "triggers"
    SUPPRESSIONS ||--o{ ALERTS : "suppresses"
```

#### Core Tables

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `users` | Dashboard users | id, username, email, password_hash, role, mfa_enabled |
| `api_keys` | API authentication | id, user_id, key_hash, scopes |
| `agents` | Registered endpoints | id, hostname, machine_guid, status, last_seen |
| `process_telemetry` | Process snapshots | id, agent_id, pid, name, cpu, memory |
| `service_telemetry` | Windows services | id, agent_id, name, status, start_type |
| `event_log` | Windows Event Logs | id, agent_id, event_id, level, message |
| `startup_inventory` | Persistence items | id, agent_id, type, path, command |
| `alerts` | Security alerts | id, agent_id, rule_id, severity, status |
| `evidence` | Alert evidence | id, alert_id, telemetry_type, raw_records |
| `audit_log` | Audit trail | id, actor_id, action, resource, result |
| `rules` | Detection rules | id, name, rule_type, condition, severity |
| `suppressions` | Alert suppressions | id, rule_id, pattern, expiry |

### 4. Windows Agent Architecture

```mermaid
graph TB
    subgraph "Agent Process"
        A[Main Loop] --> B[Config Manager]
        A --> B[Collector Manager]
        A --> C[Transport]
        A --> D[Health Monitor]
    end

    subgraph "Collectors"
        B --> E[Process Collector]
        B --> F[Service Collector]
        B --> G[EventLog Collector]
        B --> H[Startup Collector]
        B --> I[Health Collector]
    end

    subgraph "Transport"
        C --> J[HTTP Client]
        C --> K[mTLS Context]
        C --> L[Batching]
        C --> M[Compression]
    end

    subgraph "Windows APIs"
        E --> WMI[WMI/CIM]
        F --> SCM[Service Control Manager]
        G --> EVT[Event Log API]
        H --> REG[Registry/Task Scheduler]
        D --> PDH[PDH/Performance Counters]
    end
```

#### Agent Components

| Component | Responsibility |
|-----------|----------------|
| **Config Manager** | Polls backend for config, validates signatures |
| **Process Collector** | Enumerates processes via WMI, captures cmdline, hashes |
| **Service Collector** | Enumerates services via SCM, checks binary signatures |
| **EventLog Collector** | Queries Security/System/Application logs |
| **Startup Collector** | Registry Run keys, Task Scheduler, Startup folders |
| **Health Collector** | CPU, memory, disk, network, queue depth |
| **HTTP Client** | Async httpx with connection pooling |
| **mTLS Context** | Certificate validation, mutual auth |
| **Batching** | Configurable size/interval, compression |

### 5. API Communication

```mermaid
sequenceDiagram
    participant A as Agent
    participant B as Backend
    participant C as Database

    Note over A,B: Agent Registration
    A->>B: POST /agent/v1/register
    B->>C: INSERT agent
    C-->>B: Agent ID
    B-->>A: 201 Created + Agent ID

    Note over A,B: Configuration Poll
    A->>B: POST /agent/v1/config/poll
    B->>C: SELECT config
    C-->>B: Config
    B-->>A: Config + Signature

    Note over A,B: Heartbeat
    loop Every 60s
        A->>B: POST /agent/v1/heartbeat
        B->>C: UPDATE last_seen
        C-->>B: OK
        B-->>A: 200 OK
    end

    Note over A,B: Telemetry Ingestion
    loop Every 30-300s
        A->>B: POST /agent/v1/telemetry (batched)
        B->>C: BULK INSERT telemetry
        C-->>B: OK
        B-->>A: 200 OK
    end
```

### 6. Detection Engine

```mermaid
graph LR
    A[Telemetry Ingest] --> B[Rule Engine]
    B --> C{Match?}
    C -->|Yes| D[Create Alert]
    C -->|No| E[Discard]
    D --> F[Evidence Collection]
    D --> G[Alert Store]
    G --> H[Alert API]
    H --> I[Frontend Dashboard]
    F --> I
```

#### Detection Rule Types

| Type | Description | Example |
|------|-------------|---------|
| **process** | Process behavior | `cmdline contains "powershell -enc"` |
| **service** | Service anomalies | `service_type=kernel AND status=running` |
| **startup** | Persistence | `registry_key=Run AND path=temp` |
| **eventlog** | Event log patterns | `event_id=4688 AND parent=cmd.exe` |
| **correlation** | Multi-event | `process_create + network_connect` |

### 7. Alert Investigation Workflow

```mermaid
stateDiagram-v2
    [*] --> NEW: Alert Created
    NEW --> INVESTIGATING: Analyst assigns
    INVESTIGATING --> TRUE_POSITIVE: Confirmed threat
    INVESTIGATING --> FALSE_POSITIVE: Benign activity
    INVESTIGATING --> BENIGN: Legitimate activity
    INVESTIGATING --> SUPPRESSED: Known pattern
    TRUE_POSITIVE --> RESOLVED: Remediation complete
    FALSE_POSITIVE --> RESOLVED: Dismissed
    BENIGN --> RESOLVED: Acknowledged
    SUPPRESSED --> RESOLVED: Expiry or manual
    RESOLVED --> [*]
```

### 8. Data Collection Pipeline

```mermaid
graph LR
    A[Agent Collectors] --> B[Batching]
    B --> C[Compression]
    C --> D[mTLS Transport]
    D --> E[API Gateway]
    E --> F[Ingestion API]
    F --> G[Validation]
    G --> H{Valid?}
    H -->|Yes| I[Batch Processor]
    H -->|No| J[Error Log]
    I --> K[Database Writer]
    K --> L[(Database)]
    I --> M[Detection Engine]
    M --> N[Alert Generator]
    N --> O[Alert Store]
```

---

## Security Architecture

```mermaid
graph TB
    subgraph "Transport Security"
        A[mTLS Agent-Backend]
        B[TLS Frontend-Backend]
    end

    subgraph "Authentication"
        C[JWT Access Tokens 15m]
        D[Refresh Tokens 7d]
        E[Argon2id Passwords]
        F[Refresh Token Rotation]
        G[Refresh Token Revocation]
    end

    subgraph "Authorization"
        H[Role-Based: Admin/Analyst/Viewer]
        I[Permission-Based]
    end

    subgraph "Data Protection"
        J[Encryption at Rest]
        K[Secrets in Env Vars]
        L[Audit Logging]
    end

    style C fill:#ffebee
    style D fill:#ffebee
    style F fill:#c8e6c9
    style G fill:#c8e6c9
```

---

## Deployment Architecture

```mermaid
graph TB
    subgraph "Development"
        D1[Frontend Dev Server :5173]
        D2[Backend Dev Server :8000]
        D3[SQLite Database]
    end

    subgraph "Production"
        P1[Load Balancer]
        P2[Frontend: Nginx + Static Files]
        P3[Backend: Gunicorn + FastAPI Workers]
        P4[PostgreSQL Primary]
        P5[PostgreSQL Replica]
        P6[Redis Cache]
    end

    subgraph "Agent Fleet"
        A1[Endpoint 1]
        A2[Endpoint 2]
        A3[Endpoint N]
    end

    P1 --> P2
    P1 --> P3
    P3 --> P4
    P3 --> P6
    A1 -.->|mTLS| P3
    A2 -.->|mTLS| P3
    A3 -.->|mTLS| P3
```

---

## Data Flow Summary

| Flow | Frequency | Volume | Latency |
|------|-----------|--------|---------|
| Agent Heartbeat | 60s | ~1 KB | <100ms |
| Process Telemetry | 30s | ~50 KB | <500ms |
| Service Telemetry | 60s | ~10 KB | <200ms |
| Event Log | 10s | ~5 KB | <100ms |
| Startup Inventory | 3600s | ~100 KB | <1s |
| Health Metrics | 60s | ~2 KB | <100ms |
| Alert Generation | Event-driven | ~1 KB | <500ms |
| Config Poll | 300s | ~5 KB | <200ms |

---

## Scalability Considerations

| Component | Horizontal Scaling | Bottlenecks |
|-----------|-------------------|-------------|
| Frontend | CDN + Static Files | None |
| Backend API | Gunicorn Workers | Database Connections |
| Database | Read Replicas | Write Throughput |
| Agent Ingestion | Partition by Agent ID | Batch Write Throughput |
| Detection Engine | Rule Partitioning | Rule Complexity |
| WebSocket | Redis Pub/Sub | Connection Count |

---

## Monitoring & Observability

| Component | Metrics | Health Check |
|-----------|---------|--------------|
| Backend | Request latency, error rate, queue depth | `/health`, `/ready` |
| Database | Connections, query latency, size | `/ready` checks DB |
| Agent Ingestion | Events/sec, batch size, latency | Heartbeat monitoring |
| Detection Engine | Rules evaluated, alerts/sec, false positive rate | Rule evaluation latency |
| Frontend | Bundle size, load time, errors | N/A |

---

## Security Boundaries

| Boundary | Protection |
|----------|------------|
| Agent ↔ Backend | mTLS + JWT (agent identity) |
| Frontend ↔ Backend | TLS + JWT (user identity) |
| Admin ↔ Backend | TLS + JWT + MFA |
| Database | Network isolation, encryption at rest |
| Secrets | Environment variables only, never in code |

---

## File Structure Summary

```
SentinelWatch/
├── agent/                 # Windows monitoring agent (Python)
│   ├── src/sentinelwatch_agent/
│   │   ├── collectors/    # Process, Service, EventLog, Startup
│   │   ├── transport/     # mTLS, HTTP client, batching
│   │   ├── crypto/        # Certificates, signing
│   │   ├── models/        # Telemetry data models
│   │   └── main.py        # Agent entry point
│   └── tests/
├── backend/               # FastAPI Backend (Python)
│   ├── src/sentinelwatch_backend/
│   │   ├── api/v1/        # 9 router modules
│   │   ├── auth/          # JWT, passwords, tokens
│   │   ├── models/        # SQLAlchemy 2.0 models
│   │   ├── database.py    # Async engine, sessions
│   │   ├── config.py      # Pydantic Settings
│   │   ├── detection_rules/ # Rule engine
│   │   └── main.py        # FastAPI app factory
│   ├── config/            # YAML configuration
│   └── tests/
├── frontend/              # React Dashboard (TypeScript)
│   ├── src/
│   │   ├── pages/         # 13 page components
│   │   ├── components/    # shadcn/ui + custom
│   │   ├── hooks/         # Zustand stores, TanStack Query
│   │   ├── lib/           # API client, utilities
│   │   └── types/         # TypeScript definitions
│   └── package.json
├── detection_rules/       # Detection rule engine
├── docs/                  # Documentation
└── README.md
```

---

## Configuration Matrix

| Environment | Backend Debug | Frontend Dev | Database | TLS | Secrets |
|-------------|---------------|--------------|----------|-----|---------|
| Development | true | Vite Dev Server | SQLite | Optional | `.env` / Defaults |
| Testing | true | Build Preview | SQLite | Optional | `.env.test` |
| Demo | false | Build Preview | PostgreSQL | Required | `.env.demo` |
| Production | false | Nginx Static | PostgreSQL | Required | Vault/Env |

---

## Technology Stack Summary

| Category | Technology | Version |
|----------|------------|---------|
| **Frontend** | React | 18.2 |
| | TypeScript | 5.5 |
| | Vite | 5.4 |
| | Tailwind CSS | 3.4 |
| | shadcn/ui + Radix | Latest |
| | TanStack Query | 5.51 |
| | TanStack Table | 8.20 |
| | Recharts | 2.15 |
| | Zustand | 4.5 |
| **Backend** | FastAPI | 0.110+ |
| | SQLAlchemy | 2.0 |
| | Pydantic | 2.7 |
| | Pydantic Settings | 2.3 |
| | python-jose | 3.3 |
| | passlib + argon2 | Latest |
| | aiosqlite / asyncpg | Latest |
| | Uvicorn/Gunicorn | Latest |
| **Agent** | Python | 3.11+ |
| | WMI / pywin32 | Latest |
| | aiohttp / httpx | Latest |
| | cryptography | Latest |
| **Database** | PostgreSQL | 15+ |
| | SQLite (dev) | 3.35+ |
| | Alembic | 1.11+ |
| **Infrastructure** | Nginx | Latest |
| | Gunicorn | 21+ |
| | Redis | 7+ |
| | Docker | 24+ |

---

*This document represents the current system architecture as of Phase 6.5 preparation. Update with each major release.*
