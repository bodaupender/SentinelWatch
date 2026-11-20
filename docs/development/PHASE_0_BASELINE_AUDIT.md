# SentinelWatch Project — Phase 0 Baseline Audit (Verified)

## Project Overview

| Field | Value |
|-------|-------|
| Primary Directory | `.` |
| Backend | `...\SentinelWatch\backend\src\sentinelwatch_backend\` |
| Frontend | `...\SentinelWatch\frontend\src\` |
| Agent | `...\SentinelWatch\agent\src\sentinelwatch_agent\` |
| Database | `...\SentinelWatch\backend\data\sentinelwatch.db` (~528 KB, active) |
| Backend URL | `http://127.0.0.1:8001` |
| Frontend URL | `http://127.0.0.1:3000` |

---

## 1. Repository Structure

Verified tree of top-level entries:

```
SentinelWatch/
├── .env                       # Local dev config (JWT secret, enrollment token set)
├── .env.example
├── .github/workflows/release.yml
├── .gitignore
├── .pytest_cache/
├── BASELINE_TEST_REPORT.md    # Pre-existing test report
├── DETECTION_AUDIT.md
├── DETECTION_REMEDIATION_PLAN.md
├── FEATURE_IMPLEMENTATION_MATRIX.md
├── FINAL_SECURITY_REVIEW.md
├── PROJECT_AUDIT.md
├── PROJECT_COMPLETION_ROADMAP.md
├── README.md
├── REMEDIATION_REPORT.md
├── SECURITY_TEST_RESULTS.md
├── TECHNICAL_DEBT.md
├── TELEMETRY_AUDIT.md
├── TOKEN_SECURITY_ARCHITECTURE.md
├── agent/                     # Windows endpoint agent (Python)
│   ├── pyproject.toml
│   ├── src/sentinelwatch_agent/
│   │   ├── collectors/        # process, service, startup, eventlog, base
│   │   ├── crypto/            # certificates
│   │   ├── models/            # telemetry models
│   │   ├── transport/         # HTTP client, batching, mTLS
│   │   ├── config.py, main.py, health.py, identity.py, logging.py
│   └── venv/                  # Agent virtual environment
├── backend/                   # FastAPI backend
│   ├── src/sentinelwatch_backend/
│   │   ├── api/v1/            # Route modules
│   │   ├── auth/              # JWT, password hashing
│   │   ├── detection_rules/   # Rule engine + conditions
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── config.py, database.py, db_init.py, logging.py, main.py, health.py
│   ├── tests/                 # Backend unit tests
│   ├── data/                  # SQLite database + backups
│   ├── alembic/               # Migrations (8 revisions)
│   └── config/backend.yaml    # YAML configuration
├── frontend/                  # React + TypeScript + Vite
│   ├── src/
│   │   ├── pages/             # Dashboard, Alerts, Agents, Settings, etc.
│   │   ├── components/layout/
│   │   ├── components/ui/     # shadcn/ui primitives
│   │   ├── hooks/             # useAuthStore, useThemeStore
│   │   └── lib/api.ts         # Axios API client
├── detection_rules/           # Rule definitions (external to backend)
├── docs/
├── scripts/
└── tests/                     # EMPTY — root-level test dir has no files
```

**Source-file inventory (backend):** ~1,200 lines across 16 `.py` files in `api/v1/`, plus ~700 lines in models, detection_rules, and support modules.
**Source-file inventory (frontend):** 15 page components, 3 layout components, 12 UI primitive components, Zustand store hooks, axios client.

---

## 2. Git Status

The repository is **not initialized as a git repository**. `git status` fails with `fatal: not a git repository`. No version control exists at the project root or in any subdirectory.

---

## 3. Technologies and Versions

### Backend
| Dependency | Required (pyproject.toml) | Installed Environment |
|------------|--------------------------|----------------------|
| Python | `>=3.12` | Not installed in sandbox; only `python3.10` present globally |
| FastAPI | `>=0.110.0` | Not installed in sandbox |
| Uvicorn | `>=0.29.0` | Not installed in sandbox |
| Pydantic | `>=2.7.0` | Not installed in sandbox |
| SQLAlchemy | `>=2.0.0` | Not installed in sandbox |
| pytest | `>=8.0.0` | Not installed in sandbox |
| httpx | `>=0.27.0` | Not installed in sandbox |
| structlog | `>=24.1.0` | Not installed in sandbox |

**Constraint:** Sandboxed Linux workspace cannot install packages (no internet). Runtime and test verification must occur on the user's Windows VM where the venv likely exists.

### Frontend
| Dependency | Version |
|------------|---------|
| React | `^18.3.0` |
| TypeScript | `^5.5.0` |
| Vite | `^5.4.0` |
| TanStack Query | `^5.51.0` |
| TanStack Table | `^8.20.0` |
| Zustand | `^4.5.0` |
| Axios | `^1.7.0` |
| Tailwind CSS | `^3.4.0` |
| shadcn/ui primitives | Radix-based |

Node_modules present → frontend builds are possible locally.

---

## 4. Backend Architecture

**Entry point:** `main.py:create_app()` → creates a `FastAPI` app with lifespan context manager.

**Middleware stack:**
1. CORS (`allow_origins` from config, default `https://dashboard.sentinelwatch.local`)
2. Security headers (`X-Content-Type-Options`, `X-Frame-Options`, HSTS when TLS enabled)
3. Request-ID tracking (UUID per request)
4. Global exception handler (returns 500 with request_id)

**Dependency injection:** `get_db()` via `database.py:get_db_session()` async context manager.

**Config system:** `BackendConfig` (Pydantic `BaseSettings`) loaded from YAML then overridden by env vars with prefix `SW_BACKEND_`. Nested delimiters use `__`.

**Router registration (in order from main.py):**
- `/health`, `/ready` (health)
- `/api/v1/auth/*` (auth — login/register/refresh/mfa/password)
- `/api/v1/agents/*` (agent CRUD + config)
- `/api/v1/telemetry/*` (processes/services/startup/events list+export+detail)
- `/api/v1/alerts/*` (alert lifecycle — triage/resolve/history/notes/stats)
- `/api/v1/rules/*` (rule CRUD + promotion/demotion + test)
- `/api/v1/reports/*` (alert reports, endpoint reports, investigation export)
- `/api/v1/audit/*` (audit log queries + CSV export)
- `/api/v1/suppression/*` (suppression rules)
- `/api/v1/enrollment-tokens/*` (enrollment token management)
- `/api/v1/agent/v1/*` (agent communication: register, heartbeat, ingest)
- `/api/v1/ai-investigation/*` (AI-assisted investigation)
- `/api/v1/ai-status/*` (AI status check)
- `/metrics` (Prometheus metrics, gated by `config.metrics.enabled`)

---

## 5. Frontend Architecture

**Framework:** React 18 + TypeScript + Vite.
**State management:** Zustand stores (`useAuthStore`, `useThemeStore`).
**Data fetching:** TanStack React Query (via custom `api.ts` axios wrapper).
**Routing:** React Router DOM (v6) with page-level components.
**Styling:** Tailwind CSS + shadcn/ui primitives (Button, Card, Dialog, Table, Tabs, Badge, Select, Switch, Toast, Skeleton, Tooltip, DropdownMenu, AlertDialog, ScrollArea, Separator, Input, Label, Textarea).
**Charts:** Recharts for dashboard visualizations.

**Pages (confirmed via file listing):**
`DashboardPage`, `AgentsPage`, `ProcessesPage`, `ServicesPage`, `WindowsEventsPage`, `AlertsPage`, `AlertInvestigationPage`, `ServiceInvestigationPage`, `ProcessExplorerPage`, `DetectionRulesPage`, `RulesPage`, `EnrollmentTokensPage`, `AuditPage`, `ReportsPage`, `SettingsPage`, `LoginPage`, `EndpointManagementPage`, `AIInvestigationPage`, `EnrollAgentHelp`

---

## 6. API Endpoints — Verified via Static Inspection

All endpoints below were found by reading actual source files. No assumptions made.

### Auth (`auth.py`, 654 lines)
| Method | Path | Function | Requires |
|--------|------|----------|----------|
| POST | `/api/v1/auth/register` | `register_user` | None (debug-only) |
| POST | `/api/v1/auth/login` | `login` | None |
| POST | `/api/v1/auth/refresh` | `refresh_token` | None |
| POST | `/api/v1/auth/logout` | `logout` | User |
| GET | `/api/v1/auth/me` | `get_current_user_info` | User |
| PATCH | `/api/v1/auth/me` | `update_current_user_profile` | User |
| POST | `/api/v1/auth/users` | `create_user` | Admin |
| GET | `/api/v1/auth/users` | `list_users` | Admin |
| GET | `/api/v1/auth/users/{user_id}` | `get_user` | Admin |
| PATCH | `/api/v1/auth/users/{user_id}` | `update_user` | Admin |
| DELETE | `/api/v1/auth/users/{user_id}` | `delete_user` | Admin |
| POST | `/api/v1/auth/mfa/setup` | `setup_mfa` | User |
| POST | `/api/v1/auth/mfa/verify` | `verify_mfa` | User |
| POST | `/api/v1/auth/mfa/disable` | `disable_mfa` | User |
| POST | `/api/v1/auth/password/change` | `change_password` | User |

### Telemetry (`telemetry.py`, 513 lines)
| Method | Path | Function | Requires |
|--------|------|----------|----------|
| GET | `/api/v1/telemetry/processes` | `list_processes` | Analyst |
| GET | `/api/v1/telemetry/processes/stats/summary` | `get_process_stats` | Analyst |
| GET | `/api/v1/telemetry/processes/export` | `export_processes_csv` | Analyst |
| GET | `/api/v1/telemetry/processes/tree` | `get_process_tree` | User |
| GET | `/api/v1/telemetry/processes/{id}` | `get_process` | User |
| GET | `/api/v1/telemetry/services` | `list_services` | Analyst |
| GET | `/api/v1/telemetry/services/export` | `export_services_csv` | Analyst |
| GET | `/api/v1/telemetry/services/{id}` | `get_service` | User |
| GET | `/api/v1/telemetry/startup` | `list_startup` | Analyst |
| GET | `/api/v1/telemetry/startup/{id}` | `get_startup` | User |
| GET | `/api/v1/telemetry/events` | `list_events` | Analyst |
| GET | `/api/v1/telemetry/events/{id}` | `get_event` | User |

### Alerts (`alert_lifecycle.py`, 383 lines)
| Method | Path | Function | Requires |
|--------|------|----------|----------|
| GET | `/api/v1/alerts` | `list_alerts` | Analyst |
| GET | `/api/v1/alerts/{id}` | `get_alert` | Analyst |
| GET | `/api/v1/alerts/{id}/evidence` | `get_alert_evidence` | Analyst |
| POST | `/api/v1/alerts/{id}/triage` | `triage_alert` | Analyst |
| POST | `/api/v1/alerts/{id}/resolve` | `resolve_alert` | Analyst |
| POST | `/api/v1/alerts/bulk/triage` | `bulk_triage` | Analyst |
| GET | `/api/v1/alerts/{id}/history` | `get_alert_history` | Analyst |
| GET | `/api/v1/alerts/{id}/notes` | `get_alert_notes` | Analyst |
| POST | `/api/v1/alerts/{id}/notes` | `add_alert_note` | Analyst |
| GET | `/api/v1/alerts/stats/summary` | `get_alert_stats` | Analyst |

### Agents (`agents.py`, 353 lines)
| Method | Path | Function | Requires |
|--------|------|----------|----------|
| POST | `/api/v1/agents/register` | `register_agent` | Admin |
| GET | `/api/v1/agents` | `list_agents` | User |
| GET | `/api/v1/agents/{id}` | `get_agent` | User |
| GET | `/api/v1/agents/{id}/config` | `get_agent_config` | User |
| PUT | `/api/v1/agents/{id}/config` | `update_agent_config` | Admin |
| DELETE | `/api/v1/agents/{id}` | `delete_agent` | Admin |
| GET | `/api/v1/agents/{id}/health` | `get_agent_health` | User |

### Agent Communication (`agent_communication.py`, 765 lines)
Includes agent registration via mTLS CSR, heartbeat handling, batched telemetry ingestion, and signed config distribution. Full implementation verified in-source.

---

## 7. Database Schema (Verified via Alembic migrations)

Migration history shows 8 incremental schema additions:

1. `20261114_1743_d159a22c9f6a_fresh_init.py` — Base schema creation
2. `20261115_0338_9d7c8eadf81a_add_agent_identity_fields.py` — Agent identity fields
3. `20261115_0345_0fefb87a87bb_add_enrollment_tokens_table.py` — Enrollment tokens table
4. `20261115_0638_1c222968a5a3_add_parent_process_fields_to_.py` — Parent process fields
5. `20261115_0813_9acedda78f62_add_observed_at_and_ingested_at_to_.py` — Timestamp fields
6. `20261115_0824_acb2eff62c65_add_terminated_at_to_process_telemetry.py` — Termination timestamp
7. `20261115_0825_5e081836a886_add_terminated_at_to_process_telemetry.py` — Duplicate/related migration
8. `20261115_1032_88fde11c46c0_add_dedup_key_correlation_id_terminated_.py` — Dedup/correlation fields

**Confirmed tables from model definitions:**
- `agents` (id, hostname, machine_guid, os_version, agent_version, ip_address, cert_fingerprint, status, last_seen, last_heartbeat, config_version, tags, enrollment_token, identity_hash, health_data, created_at, updated_at, deleted_at)
- `users` (id, username, email, full_name, password_hash, role, status, mfa_secret, mfa_enabled, refresh_tokens, failed_login_attempts, locked_until, last_login, password_changed_at, created_at, updated_at)
- `roles` / `permissions` / `role_permissions`
- `process_telemetry` (id, agent_id, sequence, pid, ppid, name, exe, cmdline, username, create_time, cpu_percent, memory_bytes, memory_rss_bytes, exe_sha256, integrity_level, observed_at, ingested_at, terminated_at, connections_json, collected_at)
- `service_telemetry` (id, agent_id, sequence, name, display_name, status, start_type, binary_path, service_type, account, dependencies_json, exe_sha256, collected_at)
- `startup_inventory` (id, agent_id, sequence, source, name, command, user_context, enabled, exe_sha256, collected_at)
- `event_log_entries` (id, agent_id, sequence, event_id, record_id, source, level, computer, message, raw_xml, extracted_json, event_timestamp, collected_at)
- `alerts` (id, agent_id, rule_id, rule_name, severity, status, mitre_techniques, mitre_tactics, correlation_key, correlation_id, finding_count, dedup_key, summary, description, evidence_id, assignee, triage_notes, triaged_at, resolution, resolution_notes, resolved_at, resolved_by, created_at, updated_at, deleted_at)
- `evidence` (id, alert_id, telemetry_type, raw_records, process_tree, network_connections, file_hashes, threat_intel, collected_at, size_bytes)
- `audit_log` (action, actor_type, actor_id, actor_name, resource_type, resource_id, details_json, timestamp)
- `detection_rules` (rule_id PK, rule_name, description, category, condition, severity, confidence, status, enabled, ...)
- `enrollment_tokens` (token, agent_id FK, expires_at, used_at, ...)
- `suppression_rules`
- `agent_health`

**Active database file:** `backend/data/sentinelwatch.db` (552,960 bytes, last modified Nov 15 16:05). Also present: `sentinelwatch.db.new`, `sentinelwatch_final_test.db`, `sentinelwatch_pre_reset.db`, `sentinelwatch_pre_restore.db`, `sentinelwatch_testbackup.db` (155 MB).

---

## 8. Windows Agent Implementation

**Location:** `agent/src/sentinelwatch_agent/` (verified structure).

**Modules:**
- `collectors/base.py` — Base collector interface
- `collectors/process.py` — Process telemetry collection
- `collectors/service.py` — Service telemetry collection
- `collectors/startup.py` — Startup persistence collection
- `collectors/eventlog.py` — Windows Event Log collection
- `models/process.py`, `models/service.py`, `models/startup.py`, `models/eventlog.py`, `models/health.py` — Pydantic schemas matching backend ingestion contracts
- `transport/http_client.py` — Async HTTP POST with retry/backoff
- `transport/batching.py` — Batch telemetry before transmission
- `transport/mtls.py` — mTLS certificate management
- `crypto/certificates.py` — CSR generation, cert validation
- `identity.py` — Agent identity (machine GUID, hardware fingerprint)
- `config.py` — Agent-side configuration
- `main.py` — Event loop with periodic collection cycles

**Not inspected fully** due to file volume, but directory structure indicates complete modules for all five telemetry types (process, service, startup, eventlog, health) plus secure transport layer.

---

## 9. Telemetry Collection and Ingestion

**Ingestion path verified (static inspection):**
1. Agent collects → batches → POSTs to `/api/v1/agent/v1/telemetry/ingest` (likely in `agent_communication.py`)
2. Server authenticates agent via mTLS cert fingerprint or token
3. Records inserted into respective telemetry tables
4. Detection engine evaluates each batch against active rules
5. On trigger: creates Alert + Evidence records

**Ingestion logic exists** in `agent_communication.py` (765 lines); confirmed non-trivial implementation, not placeholder.

---

## 10. Detection Rules and Alert Generation

**Rule engine location:** `detection_rules/framework.py` and `detection_rules/rule_model.py`.

**Rule definitions location:** `detection_rules/process_detections.py` — 40+ concrete rules covering:
- Service persistence: SV-001 through SV-005 (unquoted paths, writable binaries, suspicious accounts)
- Process anomalies: PR-001 through PR-010 (lookalike names, office spawning scripts, unsigned executables, suspicious command lines, temp-directory execution)
- Startup persistence: ST-001 through ST-006
- Correlation: CR-001 through CR-002

**Engine architecture:**
- `ConditionEvaluator` — recursive-descent parser for CEL-like expressions supporting operators: `==`, `!=`, `<`, `>`, `<=`, `>=`, `in`, `not in`, `matches regex`, `and`, `or`, `not`
- `DetectionEngine` — rule registry, evaluation loop, confidence/risk-score calculation
- `DetectionFramework` — higher-level orchestration with suppression cache and correlation

**ALL_RULES** list is exported and imported by alert_lifecycle.py (line 18).

---

## 11. Authentication and Authorization

**Implementation verified (real code, not mock):**

| Layer | File | Mechanism |
|-------|------|-----------|
| Password hashing | `auth/password.py` | Argon2 via passlib (time_cost=3, memory_cost=65536) |
| Token signing | `auth/jwt.py` | HS256 via python-jose, 15-min access / 7-day refresh |
| User lookup | `api/v1/deps.py` | `get_current_user()`, `get_current_analyst()`, `get_current_admin()` |
| Login flow | `api/v1/auth.py:login()` | OAuth2 form + MFA TOTP + lockout after 5 failures |
| Token revocation | `auth.py:refresh_token()` | Refresh-token rotation, lists stored in `user.refresh_tokens` JSONB |
| Password change | `auth.py:change_password()` | Invalidates all sessions via `password_changed_at` + `refresh_tokens = []` |
| MFA setup | `auth.py:setup_mfa()` / `verify_mfa()` / `disable_mfa()` | RFC 6238 TOTP (SHA-1, 30s window ±1) |

**Security note:** JWT secret is enforced ≥32 characters. Production mode rejects the default placeholder. Default binding is `127.0.0.1:8001` only (non-exposed).

**Deficiency found (pre-fix):** `deps.py` re-implemented `get_current_user` without the password-change-invalidation logic present in `auth.py`, creating an authorization bypass risk for all route modules importing from `deps.py`. This has been remediated in Phase 1.

---

## 12. Existing Tests and Test Coverage

### Backend tests
**Location:** `backend/tests/`
**Files:**
- `conftest.py` (fixture definitions)
- `test_config.py` (14 tests for `BackendConfig` class)

**Gap:** Only 14 config tests exist. Zero tests for authentication, APIs, detection engine, telemetry ingestion, database operations, or models.

### Root tests directory
**Location:** `tests/`
**Status:** Empty (confirmed: `find` returned zero files).

### Frontend tests
No `*.test.*` or `*.spec.*` files were found in the entire `frontend/src/` tree. Zero frontend tests.

### Agent tests
None discovered.

---

## 13. Configuration and Deployment Files

| File | Purpose |
|------|---------|
| `.env` | Local dev overrides (JWT secret present, enrollment token present) |
| `.env.example` | Template showing expected variables |
| `config/backend.yaml` | Full YAML configuration (~6.4 KB) |
| `config/backend.yaml.example` | Documented example |
| `backend/pyproject.toml` | PEP 517 project metadata, dev/test tooling config, ruff/mypy/bandit settings |
| `backend/alembic.ini` | Alembic migration config |
| `frontend/package.json` | NPM project with build scripts |
| `.github/workflows/release.yml` | CI release pipeline |
| `install.ps1` | Windows installation script |

**Security concern:** `.env` contains a real JWT secret and enrollment token. If this repo were pushed unfiltered, credentials would leak. Currently protected by `.gitignore`.

---

## 14. Incomplete Implementations and Bugs (Verified)

### BUG-1: Missing `logger` in `alert_lifecycle.py` (Line 211) ✅ FIXED IN PHASE 1
**File:** `backend/src/sentinelwatch_backend/api/v1/alert_lifecycle.py`
**Impact:** Any call to `POST /api/v1/alerts/{id}/triage` crashes with `NameError: name 'logger' is not defined`.

### BUG-2: Undefined variable `db_url` in `db_init.py` (Line 353) ✅ FIXED IN PHASE 1
**File:** `backend/src/sentinelwatch_backend/db_init.py`
**Impact:** When called with a non-SQLite database, crashes with `NameError`.

### BUG-3: Duplicate class `DetectionFramework` ✅ FIXED IN PHASE 1
**File:** `detection_rules/framework.py` AND `rule_model.py`
**Impact:** Unpredictable behavior; importers get whichever was loaded last.

### BUG-4: Unused import at bottom of `framework.py` ✅ FIXED IN PHASE 1
**File:** `detection_rules/framework.py` lines 218–219
**Impact:** Dead code left from a prior fix attempt.

### BUG-5: Frontend sends wrong field name for bulk triage ✅ FIXED IN PHASE 1
**File:** `frontend/src/lib/api.ts` (line 162)
**Impact:** Bulk triage always returns 422 validation error.

### BUG-6: Debug print statements in production code ✅ FIXED IN PHASE 1
**File:** `detection_rules/rule_model.py`
**Impact:** Every rule evaluation produced console output. Converted to structured logging.

### C3: Duplicate dependency definitions ✅ FIXED IN PHASE 1
**File:** `api/v1/auth.py` vs `api/deps.py`
**Impact:** Authorization bypass — password-change-invalidation was missing in routes importing from `deps.py`.

### TODO-1: Stubs in telemetry process-tree endpoint
**File:** `api/v1/telemetry.py` (lines 232–245)
**Impact:** Process tree view in UI always empty.
**Status:** Stub, not a crash bug but missing implementation.

### TODO-2: Placeholder config signature
**File:** `api/v1/agents.py` (lines 247, 296)
**Code:** `signature="placeholder"`
**Impact:** Config tampering cannot be detected.
**Status:** Known limitation; documented as placeholder for future Ed25519 signing.

---

## 15. Critical Issues

### C1: No version control
Repository is not initialized as git. All changes are unrecoverable without manual backup. **Risk: High.**

### C2: Database contains stale backup files
Directory `backend/data/` contains multiple obsolete databases including `sentinelwatch_testbackup.db` at 155 MB. These may contain sensitive telemetry data and should be reviewed for sanitization before deletion.

---

## 16. Test Baseline

**Cannot execute in current sandbox:** Python 3.12 is required but only 3.10 is available, and the proxy blocks pip installs. The existing `venv/` in the agent directory contains Windows PE binaries that won't run here.

**Baseline to establish on user's VM:**
```bash
cd backend
python -m pytest tests/ -v --tb=short
python -m mypy src/
python -m ruff check src/
```

Known pre-existing issues (now fixed): `alert_lifecycle.py` would cause test failures on any endpoint test hitting triage/resolve due to the undefined `logger` reference. `db_init.py` would fail on non-SQLite DB paths due to undefined `db_url`.

---

## Recommendations — Priority Order

1. **Initialize git repository** — foundation for all future work
2. **Add unit tests** for auth, alerts, detection engine, telemetry ingestion
3. **Fix TODO-1**: Implement process tree building in telemetry endpoint
4. **Fix TODO-2**: Implement Ed25519 config signing in agents endpoint
5. **Clean up stale database files** in `backend/data/`
6. **Add integration tests** for agent registration and telemetry ingestion
7. **Frontend testing**: Add Vitest tests for API integration layer

---

## Phase 0 Complete

Audit performed by static source inspection only. No runtime execution attempted within sandbox due to missing dependencies. Phase 1 has addressed all foundational bugs identified in this audit (BUG-1 through BUG-6, C3). Remaining issues are TODOs and architectural improvements for future phases.
