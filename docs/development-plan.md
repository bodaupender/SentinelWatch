# SentinelWatch Development Plan

> **Status note:** This document's original phase checklist is historical and is not a statement of current completion. Use the [acceptance matrix](acceptance-matrix.md) for current implementation and verification status.

## Phase Overview

| Phase | Focus | Duration | Status |
|-------|-------|----------|--------|
| **Phase 1** | Architecture, Security Design & Project Foundation | Implemented; review current acceptance matrix |
| Phase 2 | Windows Agent Implementation | Implemented in source; Windows runtime verification outstanding |
| Phase 3 | Backend API & Detection Engine | Implemented in source; integration verification outstanding |
| Phase 4 | SOC Dashboard (Frontend) | Implemented in source; current production build/runtime verification outstanding |
| Phase 5 | Detection Rules & Testing | Partial; end-to-end rule and isolation validation outstanding |
| Phase 6 | Packaging, Deployment & Hardening | Partial; clean-install and Windows SCM verification outstanding |

---

## Phase 1: Architecture, Security Design & Project Foundation (Current)

### Objectives
- [x] Project structure created
- [x] Architecture documented (`docs/architecture.md`)
- [x] Threat model documented (`docs/threat-model.md`)
- [x] Security design documented (`docs/security-design.md`)
- [ ] Data flow documentation
- [ ] Dependency management (pyproject.toml, package.json)
- [ ] Configuration management framework
- [ ] Logging infrastructure
- [ ] Basic application entry points
- [ ] Health check endpoints
- [ ] Error handling framework
- [ ] Type checking configuration (mypy, tsconfig)
- [ ] Test infrastructure (pytest, vitest)
- [ ] Development scripts
- [ ] Initial README
- [ ] Validation tests pass

### Deliverables
```
SentinelWatch/
├── agent/
│   ├── pyproject.toml
│   ├── src/sentinelwatch_agent/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── health.py
│   └── tests/
├── backend/
│   ├── pyproject.toml
│   ├── src/sentinelwatch_backend/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── database.py
│   │   ├── models/
│   │   ├── api/
│   │   └── health.py
│   ├── alembic/
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   └── lib/
│   └── tests/
├── detection-rules/
│   └── README.md
├── config/
│   ├── agent.yaml.example
│   ├── backend.yaml.example
│   └── frontend.env.example
├── docs/
│   ├── architecture.md ✓
│   ├── threat-model.md ✓
│   ├── security-design.md ✓
│   ├── data-flow.md
│   └── development-plan.md (this file)
├── scripts/
│   ├── dev-start.sh
│   ├── dev-stop.sh
│   ├── test-all.sh
│   └── lint-all.sh
├── .gitignore
├── README.md
└── docker-compose.yml (optional)
```

---

## Phase 2: Windows Agent Implementation

### Objectives
- Process telemetry collector (`psutil`)
- Windows service collector (`pywin32`)
- Startup inventory collector (registry, scheduled tasks)
- Windows Event Log collector (`win32evtlog`)
- Telemetry batching & compression (zstd)
- mTLS client with certificate management
- Agent registration & enrollment flow
- Configuration polling with signature verification
- Self-health monitoring (CPU, memory, disk, network)
- Graceful shutdown & restart handling
- Windows service installation (NSSM or native)
- PyInstaller packaging spec

### Key Components
```
agent/src/sentinelwatch_agent/
├── collectors/
│   ├── __init__.py
│   ├── process.py
│   ├── service.py
│   ├── startup.py
│   └── eventlog.py
├── transport/
│   ├── __init__.py
│   ├── http_client.py
│   ├── mtls.py
│   └── batching.py
├── crypto/
│   ├── __init__.py
│   ├── certs.py
│   └── signing.py
├── config/
│   ├── __init__.py
│   ├── loader.py
│   └── validator.py
└── service/
    ├── __init__.py
    ├── install.py
    └── watchdog.py
```

---

## Phase 3: Backend API & Detection Engine

### Objectives
- FastAPI application with OpenAPI docs
- Database models (SQLAlchemy 2.0 + Alembic)
- Agent registration & management API
- Telemetry ingestion endpoints (process, service, startup, events)
- Detection engine (rule evaluation, alert generation)
- Alert management API (CRUD, triage, correlation)
- Evidence storage & retrieval
- JWT authentication with RBAC
- Audit logging (immutable)
- WebSocket for real-time alerts
- Configuration distribution API
- Rate limiting & circuit breakers
- Prometheus metrics endpoint
- Health/readiness probes

### Key Components
```
backend/src/sentinelwatch_backend/
├── api/
│   ├── __init__.py
│   ├── v1/
│   │   ├── __init__.py
│   │   ├── agents.py
│   │   ├── telemetry.py
│   │   ├── alerts.py
│   │   ├── rules.py
│   │   ├── audit.py
│   │   └── auth.py
│   └── deps.py
├── models/
│   ├── __init__.py
│   ├── agent.py
│   ├── telemetry.py
│   ├── alert.py
│   ├── rule.py
│   └── audit.py
├── detection/
│   ├── __init__.py
│   ├── engine.py
│   ├── rules/
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   ├── compiler.py
│   │   └── builtins/
│   └── correlation.py
├── services/
│   ├── __init__.py
│   ├── agent_mgmt.py
│   ├── alert_mgmt.py
│   └── config_dist.py
├── database.py
├── auth.py
├── audit.py
└── metrics.py
```

---

## Phase 4: SOC Dashboard (Frontend)

### Objectives
- React 18 + TypeScript + Vite setup
- Tailwind CSS + shadcn/ui component library
- Authentication flow (login, refresh, logout, MFA)
- Agent inventory page (table + detail drawer)
- Process explorer (searchable, filterable, sortable table)
- Service monitor (cross-agent service view)
- Alert console (triage workflow: new → investigating → resolved)
- Detection rules manager (view, test, enable/disable)
- Audit log viewer (search, filter, export)
- Settings page (user mgmt, agent config, integrations)
- Real-time updates via WebSocket
- Responsive design (desktop + tablet)
- Dark/light theme
- Accessibility (WCAG 2.1 AA)

### Key Components
```
frontend/src/
├── components/
│   ├── ui/              # shadcn/ui components
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   ├── Header.tsx
│   │   └── Layout.tsx
│   ├── agents/
│   │   ├── AgentTable.tsx
│   │   ├── AgentDetail.tsx
│   │   └── AgentStatus.tsx
│   ├── processes/
│   │   ├── ProcessTable.tsx
│   │   ├── ProcessDetail.tsx
│   │   └── ProcessTree.tsx
│   ├── alerts/
│   │   ├── AlertTable.tsx
│   │   ├── AlertDetail.tsx
│   │   ├── AlertTimeline.tsx
│   │   └── TriageActions.tsx
│   ├── rules/
│   │   ├── RuleTable.tsx
│   │   ├── RuleEditor.tsx
│   │   └── RuleTester.tsx
│   └── audit/
│       └── AuditTable.tsx
├── pages/
│   ├── Dashboard.tsx
│   ├── Agents.tsx
│   ├── Processes.tsx
│   ├── Services.tsx
│   ├── Alerts.tsx
│   ├── Rules.tsx
│   ├── Audit.tsx
│   └── Settings.tsx
├── hooks/
│   ├── useAuth.ts
│   ├── useWebSocket.ts
│   ├── useAgents.ts
│   ├── useProcesses.ts
│   └── useAlerts.ts
├── lib/
│   ├── api.ts
│   ├── auth.ts
│   ├── utils.ts
│   └── validators.ts
└── types/
    ├── agent.ts
    ├── process.ts
    ├── alert.ts
    └── rule.ts
```

---

## Phase 5: Detection Rules & Testing

### Objectives
- Rule DSL specification (YARA-L inspired)
- Built-in rule library (MITRE ATT&CK mapped)
- Rule testing framework (unit + integration)
- Historical data replay for rule validation
- False positive tracking & auto-tuning
- Rule versioning & rollback
- Staging → production promotion
- End-to-end integration tests
- Load testing (agent simulation)
- Chaos engineering (agent disconnect, backend restart)
- Security testing (penetration test scope)

### Rule Categories
| Category | MITRE Techniques | Example Rules |
|----------|------------------|---------------|
| Process Anomalies | T1055, T1059, T1218 | Suspicious parent (cmd.exe → powershell), LOLBins |
| Service Anomalies | T1543, T1569 | New service with unsigned binary, modified binpath |
| Startup Persistence | T1547, T1053 | New Run key, scheduled task with suspicious action |
| Event Log Signatures | T1059, T1569 | 4688 with encoded command, 7045 service install |
| Network Anomalies | T1071, T1572 | Process connecting to rare ports, beaconing |

---

## Phase 6: Packaging, Deployment & Hardening

### Objectives
- PyInstaller spec for agent (single executable)
- Docker images for backend + frontend
- docker-compose for local development
- Kubernetes manifests (Helm charts) for production
- CI/CD pipeline (GitHub Actions)
- Security scanning (SAST, DAST, container scan)
- Performance benchmarking
- Documentation (deployment, operations, API)
- Runbook for common operations
- Backup/restore procedures
- Upgrade/downgrade procedures

---

## Milestones & Approval Gates

| Gate | Criteria | Approver |
|------|----------|----------|
| Phase 1 → 2 | Architecture docs complete, foundation code runs, tests pass | User |
| Phase 2 → 3 | Agent collects all telemetry types, sends to backend, mTLS works | User |
| Phase 3 → 4 | Backend API complete, detection engine runs, auth works | User |
| Phase 4 → 5 | Dashboard functional, all pages work, real-time updates | User |
| Phase 5 → 6 | Rules detect test cases, E2E tests pass, load test passes | User |
| Phase 6 → Done | Packaged, deployed, documented, security scanned | User |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Windows API complexity | High | High | Incremental collector development, extensive testing |
| mTLS certificate management | Medium | High | Use established library (cryptography), automated renewal |
| Detection rule false positives | High | Medium | Staging environment, FP feedback loop, severity tiers |
| Frontend complexity | Medium | Medium | shadcn/ui components, incremental page development |
| Database migrations | Low | High | Alembic with thorough testing, backup before migrate |
| Agent performance on endpoints | Medium | High | Configurable intervals, resource limits, profiling |

---

## Current Phase 1 Next Steps

1. Create `data-flow.md` documentation
2. Create `pyproject.toml` for agent and backend
3. Create `package.json`, `tsconfig.json`, `vite.config.ts`, `tailwind.config.js` for frontend
4. Create configuration loaders (YAML + env vars)
5. Create logging infrastructure (structured JSON, levels, rotation)
6. Create basic entry points with health checks
7. Create error handling framework
8. Create mypy/tsconfig strict configs
9. Create pytest/vitest test infrastructure
10. Create development scripts
11. Create README.md
12. Run validation tests
13. Generate Phase 1 completion report
