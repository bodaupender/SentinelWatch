# SentinelWatch — Feature Implementation Matrix

**Date**: 2026-11-14
**Method**: Code-inspection classification against project requirements

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Implemented & verified (code present, test exists or manually confirmed) |
| ⚠️ | Implemented but unverified (code present, no matching test, logic looks sound) |
| 🟡 | Partially implemented (stub, TODO, or incomplete flow) |
| ❌ | Missing (no code, no stub) |
| 🔴 | Broken (compilation error, runtime crash, or dead logic) |
| ⛔ | Security risk (vulnerable pattern or missing protection) |

---

## A. Endpoint Agent

| # | Feature | Status | File(s) | Notes |
|---|---------|--------|---------|-------|
| A-1 | Process telemetry collection | ✅ | `agent/collectors/process.py` | psutil-based; dedup+redaction+hash |
| A-2 | Service telemetry collection | ✅ | `agent/collectors/service.py` | Enumerate + status tracking |
| A-3 | Startup inventory collection | ✅ | `agent/collectors/startup.py` | Registry, tasks, folders, WMI |
| A-4 | EventLog collection | ✅ | `agent/collectors/eventlog.py` | Security/System/Application channels |
| A-5 | mTLS client auth | 🟡 | `agent/crypto/certificates.py` | Key generation works; CSR→cert issuance absent |
| A-6 | Secret redaction from cmdline | ✅ | `agent/config.py` redaction patterns | 8 regex patterns applied |
| A-7 | Configurable collection intervals | ✅ | `agent/config.py`, `main.py` | 6 interval fields in config |
| A-8 | Batching + compression | ✅ | `transport/batching.py` | Max-size/interval flush policy |
| A-9 | Health reporting loop | ✅ | `main.py:_health_collection_loop` | CPU/mem/disk/net per 60s |
| A-10 | Windows service install command | ❌ | `main.py:create_argument_parser` | Prints "not yet implemented" |
| A-11 | Config push / apply on poll | 🔴 | `main.py:_config_poll_loop:330` | `_on_config_received` is a TODO |

## B. Backend API

| # | Feature | Status | File(s) | Notes |
|---|---------|--------|---------|-------|
| B-1 | RESTful OpenAPI spec | ✅ | `backend/main.py` | Swagger/redoc in debug mode |
| B-2 | JWT access + refresh tokens | ✅ | `auth/jwt.py`, `api/v1/auth.py` | httpOnly cookie rotation |
| B-3 | Password hash (Argon2id) | ✅ | `auth/password.py` | bcrypt fallback supported |
| B-4 | MFA TOTP setup/verify/disable | ✅ | `api/v1/auth.py:612-654` | Counter-window ±1 |
| B-5 | RBAC (admin/analyst/viewer/agent) | ✅ | `models/user.py`, `api/deps.py` | Permission list per role |
| B-6 | Role-permission join table | ⚠️ | `models/role.py` | DB schema ready; seed script absent |
| B-7 | Rate limiting middleware | ❌ | N/A | Config present; impl not started |
| B-8 | WebSocket live alert stream | ❌ | N/A | Config present; never wired |
| B-9 | Prometheus metrics endpoint | ⚠️ | `main.py:141-143` | Mount point only; no instrumented counters |
| B-10 | CORS security headers | ✅ | `main.py:80-89` | X-Frame, X-XSS, CSP missing |
| B-11 | Request-ID middleware | ✅ | `main.py:92-100` | Passed through response header |
| B-12 | Global exception handler | ✅ | `main.py:103-119` | Returns JSON with request_id |
| B-13 | Structured JSON logging | ✅ | `logging.py` | structlog with rotation |
| B-14 | Async SQLAlchemy engine | ✅ | `database.py` | aiosqlite pool configured |

### B-15 to B-24 — Data ingestion

| # | Feature | Status | File(s) | Notes |
|---|---------|--------|---------|-------|
| B-15 | Agent registration via token | ✅ | `api/v1/agent_communication.py:125-198` | Enrollment-token verification |
| B-16 | Agent heartbeat | ✅ | `agent_communication.py:201-238` | Updates last_seen/health_data |
| B-17 | Process telemetry batch submit | ✅ | `agent_communication.py:241-383` | Field remap + hash extract |
| B-18 | Service telemetry batch submit | ✅ | Same as above | Subtype dispatch |
| B-19 | Startup telemetry batch submit | ✅ | Same as above | Extra-field pruning |
| B-20 | EventLog batch submit | ✅ | Same as above | Channel→source rename |
| B-21 | Telemetry decompression (zstd) | 🟡 | `agent_communication.py:274-286` | Import-error raises 400; silent if lib absent |
| B-22 | Datetime normalization | ✅ | `agent_communication.py:298-301` | ISO → timezone-aware |
| B-23 | Alert creation on ingestion | 🔴 | `agent_communication.py:374` | `alerts_created = 0` placeholder |
| B-24 | Config signing (Ed25519/RSA-PSS) | 🔴 | `agent_communication.py:161,196` | Literal `"placeholder"` string |

## C. Detection Engine

| # | Feature | Status | File(s) | Notes |
|---|---------|--------|---------|-------|
| C-1 | Rule model (DetectionRule) | ✅ | `detection_rules/rule_model.py` | Pydantic v2 with validators |
| C-2 | Built-in rule definitions (23 rules) | ✅ | `detection_rules/process_detections.py` | PR/SV/ST/CR categories |
| C-3 | Rule engine evaluation loop | 🔴 | `rule_model.py:351-357` | `_evaluate_condition` always returns False |
| C-4 | CEL/YARA-L expression evaluator | ❌ | N/A | Comment only; no parser |
| C-5 | Duplicate suppression window | ⚠️ | `rule_model.py:179-183` | Suppression expiry model only; not invoked in pipeline |
| C-6 | MITRE ATT&CK mapping storage | ✅ | Model + process_detections.py | Techniques/tactics stored in JSONB |
| C-7 | FP rate tracking per rule | ✅ | `rule_model.py:132-137` | record_false_positive() defined |
| C-8 | Evaluation time benchmarking | ✅ | `rule_model.py:126-130` | avg_evaluation_time_ms tracked |
| C-9 | Rule promotion (staging → active) | ✅ | `api/v1/rules.py:409-433` | Admin-only; timestamps recorded |
| C-10 | Rule testing against sample telemetry | ⚠️ | `rules.py:353-406` | Works for rules with evaluate_all flag |

## D. Alert Management

| # | Feature | Status | File(s) | Notes |
|---|---------|--------|---------|-------|
| D-1 | Alert CRUD (SQLAlchemy) | ✅ | `models/alert.py` | Soft-delete, indexed |
| D-2 | Alert triage endpoint | ✅ | `alert_lifecycle.py:174-213` | Status transition + audit log |
| D-3 | Alert resolve endpoint | 🔴 | `alert_lifecycle.py:248-263` | Body-mutation bug; malformed response |
| D-4 | Bulk triage | ✅ | `alert_lifecycle.py:260-295` | Batch update + commit |
| D-5 | Alert evidence storage | ✅ | `models/alert.py:Evidence` | JSONB raw_records, process_tree, network_connections |
| D-6 | Evidence retrieval by alert | ✅ | `alert_lifecycle.py:144-171` | Linked via alert_id FK |
| D-7 | Alert history (audit trail) | ✅ | `alert_lifecycle.py:298-317` | Queries AuditLog for action filter |
| D-8 | Alert notes (read/write) | ✅ | `alert_lifecycle.py:320-359` | Stored as AuditLog events |
| D-9 | Alert stats summary | ✅ | `alert_lifecycle.py:362-383` | Group-by severity/status counts |
| D-10 | Alert CSV export | ✅ | `reports.py:207-263` | StreamingResponse CSV download |

## E. AI Investigation

| # | Feature | Status | File(s) | Notes |
|---|---------|--------|---------|-------|
| E-1 | Ollama connectivity check | ✅ | `ai_investigation.py:27-56` | Tags + ps endpoints polled |
| E-2 | Alert investigation prompt | ✅ | `ai_investigation.py:75-159` | Telemetry snapshot window ±30 min |
| E-3 | Evidence-boundary validation | ✅ | `ai_investigation.py:149-153` | allowed_ids set; rejects unknown IDs |
| E-4 | JSON output parsing | ✅ | `ai_investigation.py:144-148` | format=json request + json.loads response |
| E-5 | Frontend AI investigation UI | 🔴 | `frontend/src/pages/AIInvestigationPage.tsx` | Stub rendering plain text only |
| E-6 | Multi-provider support (OpenAI etc.) | ❌ | `ai_investigation.py:32-34` | Explicitly blocks non-Ollama providers |

## F. SOC Dashboard (Frontend)

| # | Feature | Status | File(s) | Notes |
|---|---------|--------|---------|-------|
| F-1 | Login page + form validation | ✅ | `pages/LoginPage.tsx` | Username/password/MFA fields |
| F-2 | Auth store (Zustand persist) | ✅ | `hooks/useAuthStore.ts` | accessToken localStorage + refresh |
| F-3 | Dark/light theme toggle | ✅ | `hooks/useThemeStore.ts` | CSS variable swap |
| F-4 | Protected/public route guards | ✅ | `App.tsx:21-55` | Redirect based on isAuthenticated |
| F-5 | Dashboard overview (KPI cards) | ⚠️ | `pages/DashboardPage.tsx` | Static chart scaffolding; data may be stale |
| F-6 | Agent inventory table | ✅ | `pages/AgentsPage.tsx` | Pagination, search, status filter |
| F-7 | Process explorer (table + tree) | ⚠️ | `pages/ProcessExplorerPage.tsx` | Tree always empty from backend |
| F-8 | Service monitor table | ✅ | `pages/ServicesPage.tsx` | Status filter + export CSV |
| F-9 | Alert console (triage workflow) | ✅ | `pages/AlertsPage.tsx` | Bulk actions + detail panel |
| F-10 | Alert investigation panel | ✅ | `pages/AlertInvestigationPage.tsx` | Evidence view + AI report area |
| F-11 | EventLog viewer | ✅ | `pages/WindowsEventsPage.tsx` | Channel/sourced event ID filters |
| F-12 | Detection rules manager | ✅ | `pages/DetectionRulesPage.tsx` | Create/test/promote UI |
| F-13 | Audit log viewer | ✅ | `pages/AuditPage.tsx` | Search + date range + CSV |
| F-14 | Reports page (charts) | ✅ | `pages/ReportsPage.tsx` | Recharts time-series charts |
| F-15 | Settings page (user mgmt) | ⚠️ | `pages/SettingsPage.tsx` | Partial forms; MFA disable edge cases |
| F-16 | Endpoint enrollment help modal | ✅ | `components/EnrollAgentHelp.tsx` | Token provisioning walkthrough |

## G. Configuration & Deployment

| # | Feature | Status | File(s) | Notes |
|---|---------|--------|---------|-------|
| G-1 | YAML config file loading | ✅ | `backend/config.py:load_from_file` | ruamel.yaml preserve_quotes |
| G-2 | Env-var override (`SW_BACKEND_*`) | ✅ | `config.py:BackendConfig.model_config` | Nested delimiter `__` |
| G-3 | `.env` secret management | ✅ | Project root `.env` | Listed in .gitignore |
| G-4 | One-command install script | ✅ | `install.ps1` | Creates venv, generates JWT key |
| G-5 | GitHub release workflow | ✅ | `.github/workflows/release.yml` | Tag → tests → zip artifact |
| G-6 | Docker build | ❌ | N/A | Not present |
| G-7 | CI pipeline (lint/test/build) | ❌ | N/A | No pre-merge CI |
| G-8 | Migration tooling (Alembic) | ❌ | N/A | No alembic.ini or env.py |

## H. Testing

| # | Feature | Status | File(s) | Notes |
|---|---------|--------|---------|-------|
| H-1 | Backend config unit tests | ✅ | `backend/tests/test_config.py` | 15 tests, all green |
| H-2 | Agent collector tests | ⚠️ | `agent/tests/test_collectors.py` | Exists; mocks psutil; needs review |
| H-3 | API route tests | ❌ | N/A | Zero endpoint tests |
| H-4 | Detection engine tests | ❌ | N/A | None |
| H-5 | Frontend component tests | ❌ | N/A | Vitest installed; zero specs |
| H-6 | E2E integration tests | ❌ | `tests/` dir empty | None |

## I. Security Controls

| # | Control | Status | File(s) | Notes |
|---|---------|--------|---------|-------|
| I-1 | mTLS between agent ↔ backend | 🟡 | `crypto/certificates.py` | Key gen works; cert issuance stubbed |
| I-2 | Password hashing Argon2id | ✅ | `auth/password.py` | Correct iterations/memory |
| I-3 | JWT short-lived access token | ✅ | `auth/jwt.py` | 15 min default |
| I-4 | Refresh token rotation | ✅ | `auth.py:366-369` | Old token removed before new added |
| I-5 | Session invalidation on password change | ✅ | `auth.py:651-652` | `refresh_tokens = []` cleared |
| I-6 | Brute-force lockout | ✅ | `auth.py:257-259` | 5 failures → 15 min lock |
| I-7 | Input validation (Pydantic) | ✅ | All router request models | Strict schemas |
| I-8 | Secret redaction in logs | ✅ | `agent/config.py` redaction patterns | 8 regex rules |
| I-9 | Audit log immutability (WORM) | ⚠️ | `models/audit.py` | No-delete enforced; file-level protections absent |
| I-10 | CORS origin allowlist | ✅ | `config.py:CORSConfig.allowed_origins_list` | Default restricts to dashboard URL |
| I-11 | Content-Security-Policy header | ❌ | `main.py:security_headers` | Not emitted |
| I-12 | HTTP Strict-Transport-Security | ⚠️ | `main.py:88` | Only when `tls.enabled=True`; dev env won't set it |
| I-13 | Rate limiting | ❌ | N/A | Config field; no middleware |
