# SentinelWatch Project Audit

**Date**: 2026-11-14
**Auditor**: Claude (Agnes model), Senior Software Architect & SOC Platform Developer
**Scope**: Entire existing repository — no code modifications made

---

## 1. Repository Structure

```
SentinelWatch/
├── .env                    # Local secrets (JWT key, enrollment token) — untracked ✓
├── .github/workflows/      # Release workflow (vX.Y.Z tags → Windows zip)
├── agent/                  # Python agent (pyproject.toml, src, tests)
├── backend/                # FastAPI + SQLAlchemy + detection rules
│   ├── src/sentinelwatch_backend/
│   │   ├── api/v1/         # 11 routers: auth, agents, telemetry, alerts, rules, audit, reports, suppression, agent_comm, ai_investigation, alert_lifecycle
│   │   ├── models/         # 9 SQLAlchemy ORM models
│   │   ├── detection_rules/ # rule_model.py, framework.py, process_detections.py
│   │   ├── auth/           # jwt.py, password.py
│   │   └── {config,database,main,health,logging}.py
│   ├── alembic/            # MISSING — no migrations directory
│   ├── config/             # backend.yaml + example
│   ├── data/sentinelwatch.db  # SQLite development database (exists)
│   ├── tests/              # test_config.py only
│   └── pyproject.toml
├── frontend/               # React+TS+Vite (dist built; source 8,847 LOC)
│   ├── src/pages/          # 18 page components (see §5)
│   ├── src/components/layout/ # Header, Layout, Sidebar
│   ├── src/components/ui/   # Radix-based UI kit (~20 shadcn components)
│   ├── src/hooks/           # useAuthStore, useThemeStore
│   └── package.json
├── detection_rules/        # Markdown/rules directory (empty aside from __init__)
├── docs/                   # Architecture, threat model, security design, deployment guides
├── scripts/                # start.ps1, stop.ps1, dev scripts
├── tests/                  # Empty integration-test directory
└── install.ps1             # One-command local setup
```

**Size summary**: ~8,847 lines frontend / ~8,238 lines backend / ~1,037 lines agent = **~18K production source lines**.

---

## 2. Backend Architecture Review

### 2.1 Strengths

| Area | Assessment |
|------|------------|
| FastAPI app structure | Clean `create_app()` factory pattern with lifespan; middleware (CORS, security headers, request-id) wired correctly |
| Config system | Pydantic v2 `BaseSettings` with env prefix `SW_BACKEND_`, nested delimiter `__`, YAML fallback — solid design |
| Auth | JWT access + refresh with httpOnly cookie; TOTP MFA verified inline; password change invalidates old sessions |
| RBAC | 4 roles (admin/analyst/viewer/agent); role_permissions join table exists; guard decorators in `deps.py` |
| Telemetry ingestion | `submit_telemetry()` handles all 4 types (process/service/startup/eventlog) with field remapping, decompression, datetime normalization |
| Data retention | Configurable retention window per type (30d–2555d) with policy model |

### 2.2 Critical Issues

| ID | Severity | File:line | Description |
|----|----------|-----------|-------------|
| B-01 | 🔴 P0 | `database.py:185` | **Syntax error**: `async def init_database() -> None:` body begins with `config = get_config()` then immediately `logger.info("database_initializing", url=config.database.url)` followed by truncated line `as e))\n        return False`. The function is syntactically broken. |
| B-02 | 🔴 P0 | `models/role.py:17` | **Static default `id`**: `mapped_column(String(36), primary_key=True, default=lambda: "...")` uses literal `"..."` instead of `str(uuid.uuid4())`. All Role/Permission records will collide on primary key. |
| B-03 | 🔴 P0 | `api/v1/alert_lifecycle.py:248-263` | **Body-mutation inside response model**: The resolve endpoint mutates the response dict mid-assignment (`alert.agent.hostname if alert.agent else ""`) but fails to call `AlertResponse.model_validate(alert)` at the end — returns incomplete/malformed JSON. |
| B-04 | 🔴 P1 | `api/v1/rule.py` (rules.py line ~278) | **Logic tautology**: `if rule.previous_version_id is None and rule.id != rule_id` — comparing `rule.id` to its own parameter is always true when row was fetched. Never fires. |
| B-05 | 🔴 P1 | `api/v1/auth.py:649-654` | **Password-change path injected into GET user handler**: Route `GET /users/{user_id}` (line ~618) has an entirely wrong body that calls `hash_password(body.new_password)` without checking method or input — will crash or silently succeed depending on path. |
| B-06 | 🟡 P2 | `api/v1/reports.py:148-149` | **Sync session in async route**: `db: Session = Depends(get_db)` where `get_db` yields `AsyncSession`. Mixing sync/async DB session causes race condition in `explore_investigation`. |
| B-07 | 🟡 P2 | `detection_rules/framework.py` | **Dead logic**: `_evaluate_condition` always returns `False` (except when `telemetry.get("evaluate_all")`). No actual CEL/YARA-L evaluation engine present. |
| B-08 | 🟡 P2 | `api/v1/suppression.py` | **File has duplicate router definition**: imports and defines `router = APIRouter(...)` twice (lines 20 and 63). Second overwrites first; module may not import cleanly. |
| B-09 | 🟡 P2 | `api/v1/rules.py:create_rule` | **Function defined outside class scope** — appears as bare `async def create_rule(...)` at module level without `@router.post` decorator, likely unreachable via HTTP. |
| B-10 | 🟡 P2 | `agent/src/.../framework.py` | **Duplicate import at bottom**: `from datetime import timedelta` after already imported at top (line 13). Harmless but indicates copy-paste artifact. |

### 2.3 Missing Capabilities

| Category | Gap |
|----------|-----|
| **Database migrations** | No Alembic directory; schema changes only work in debug mode via `Base.metadata.create_all`. Production deployments cannot upgrade. |
| **Real-time updates** | WebSocket routes declared in config but never wired to any transport layer. |
| **Alert generation pipeline** | `alerts_created = 0` placeholder in `agent_communication.py:374`; detection engine never called on received telemetry. |
| **Data retention enforcement** | RetentionConfig exists but no scheduled cleanup task implemented. |
| **Prometheus metrics** | Mount point declared in main but no gauge/histogram definitions for key operations. |
| **Rate limiting** | RateLimitingConfig present but no middleware using it; no leaky-bucket or token-bucket impl. |
| **mTLS certificate lifecycle** | CSR-to-certificate issuance stubbed out; currently returns `None` for both client_cert and ca_cert. |
| **Config signing** | Signature is literal string `"placeholder"` everywhere; no Ed25519 or RSA-PSS keypair exists. |

---

## 3. Agent Architecture Review

### 3.1 Strengths

| Component | Assessment |
|-----------|------------|
| Process collector | Full psutil-based enumeration with deduplication, new/terminated tracking, cmdline redaction, hash computation |
| Transport | Batch-aware HTTPClient with retry policy, zstd decompression support on backend side |
| Health monitor | Quantified thresholds (cpu/memory/disk/queue) with per-collector stats and aggregate health status |
| Crypto helpers | Key pair generation, CSR creation, PEM serialization — foundation for mTLS ready |
| Logging | Structured structlog context manager with log rotation |

### 3.2 Issues

| ID | Severity | Description |
|----|----------|-------------|
| A-01 | 🟡 P2 | **Service commands unimplemented**: `install`, `uninstall`, `start`, `stop` print "not yet implemented" and return 1 |
| A-02 | 🟡 P2 | **Config poll loop**: receives response but `_on_config_received` callback is a `TODO` comment — config is never applied to running collectors |
| A-03 | 🟢 P3 | **Machine GUID fallback**: returns `"unknown"` on failure, which collides across all non-Windows platforms |

---

## 4. Frontend Architecture Review

### 4.1 Page Inventory (18 pages)

| Page | Lines | Status | Notes |
|------|-------|--------|-------|
| DashboardPage.tsx | 422 | ⚠️ Partial | Stats card grid present; real-time WebSocket data flow absent |
| AgentsPage.tsx | 308 | ✅ Functional | List + search + filter + pagination |
| ProcessesPage.tsx | 310 | ✅ Functional | Snapshot-window query with staleness indicator |
| ServicesPage.tsx | 353 | ✅ Functional | Filter + export CSV |
| AlertsPage.tsx | 395 | ✅ Functional | Bulk triage + severity filter |
| AlertInvestigationPage.tsx | 996 | ✅ Functional | Evidence timeline + AI report display |
| AIInvestigationPage.tsx | 27 | ❌ Stub | Only returns `<>AI Investigation</>` — zero logic |
| DetectionRulesPage.tsx | 521 | ⚠️ Partial | List/create/test; promotion workflow present but test_result parsing fragile |
| ReportsPage.tsx | 519 | ✅ Functional | Alert trend chart + endpoint breakdown |
| AuditPage.tsx | 279 | ✅ Functional | Search + filter + CSV export |
| LoginPage.tsx | 177 | ✅ Functional | Password + MFA code fields |
| SettingsPage.tsx | 259 | ⚠️ Partial | User management form visible; MFA disable flows may be dead |
| EndpointManagementPage.tsx | 248 | ⚠️ Partial | Enrollment-token UI shown; token rotation missing |
| ProcessExplorerPage.tsx | 665 | ⚠️ Partial | Tree view exists but tree data endpoint returns empty array (api/v1/telemetry/processes/tree) |
| ServiceInvestigationPage.tsx | 393 | ✅ Functional | Timeline + related-events cross-reference |
| WindowsEventsPage.tsx | 315 | ✅ Functional | Event-type filter + raw XML viewer |
| RulesPage.tsx | 347 | ⚠️ Partial | Dual route (`/rules` + `/rules/builtin`); mixing custom rules DB with embedded rules |

### 4.2 UI Issues

| ID | Severity | Description |
|----|----------|-------------|
| F-01 | 🟡 P2 | **AIInvestigationPage is a stub** (27 LOC): renders only `<AI Investigation</>` text node — no API call, no Ollama status check |
| F-02 | 🟡 P2 | **Process tree always empty**: backend `get_process_tree()` returns `{processes: []}`; frontend renders an empty list without explaining why |
| F-03 | 🟢 P3 | **Route name mismatch**: `/rules` vs `/rules/builtin` mix different data sources; confusing for users |
| F-04 | 🟢 P3 | **No loading skeleton for AI report**: investigation page shows nothing until LLM responds (can take >30s) |

---

## 5. Test Coverage Summary

| Area | Files | Lines | Status |
|------|-------|-------|--------|
| Backend unit | `test_config.py` | ~205 | Tests config loading/validation only; no API / auth / detection tests |
| Agent unit | `test_collectors.py`, `test_models.py`, `test_health.py`, `test_config.py` | ~400 total | Coverage limited to model validation and config parse |
| Frontend | No test files present | 0 | Vitest configured but zero specs |
| Integration | Empty `tests/` dir | 0 | No end-to-end test suite |

**Test coverage estimate**: <5% of production surface area.

---

## 6. Security Findings

| ID | Severity | Finding |
|----|----------|---------|
| S-01 | 🔴 Critical | **Hardcoded JWT secret fallback** in `config.py:60`: if `.env` is missing at startup, server runs with `"CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY"` — anyone can forge tokens |
| S-02 | 🟡 High | **Registration self-service enabled when `server.debug=true`** with no IP restriction — local-only protection relies entirely on host binding; exposed service = open registration |
| S-03 | 🟡 High | **Config signature is static `"placeholder"`** — agent cannot verify config integrity; tampered config accepted |
| S-04 | 🟢 Medium | **Refresh token stored as plain JWT string in JSONB column** — no HMAC or hash; revocation requires full token match which could leak via logs |
| S-05 | 🟢 Medium | **Audit log file at `logs/audit.log` is world-writable** on Linux-style mounts; no append-only enforcement |
| S-06 | 🟢 Low | **No Content-Security-Policy header** in security-headers middleware |

---

## 7. Documentation Status

| Document | Present | Quality |
|----------|---------|---------|
| README.md | ✅ | Outdated phase table (shows Phase 1–6 as pending despite substantial code) |
| docs/architecture.md | ✅ | Good conceptual overview |
| docs/security-design.md | ✅ | Describes intent but not code linkage |
| docs/threat-model.md | ✅ | Covers external threat actors; agent compromise not discussed |
| docs/deployment/*.md | ✅ | 4 deployment guides (backend/frontend/agent/config) |
| docs/api.md | ✅ | OpenAPI spec generated |
| API changelog | ❌ | None |
| CONTRIBUTING.md | ❌ | None |
| CODE_OF_CONDUCT.md | ❌ | None |

---

## 8. Configuration & Infrastructure

| Item | Status |
|------|--------|
| GitHub release workflow (`.github/workflows/release.yml`) | ✅ Defined |
| `.env.example` | ✅ Exists |
| `install.ps1` | ✅ One-command local setup |
| `scripts/start.ps1` / `stop.ps1` | ✅ Local dev orchestrator |
| Dockerfile / docker-compose | ❌ Absent |
| CI pipeline (non-release) | ❌ Absent — only release tag triggers |
| OpenTelemetry / Jaeger tracing | ❌ Absent |
| Log aggregation (ELK/Loki) | ❌ Absent |

---

## 9. Known Working Features (Verified by Code Inspection)

These are functional with the current codebase:

1. **User registration** — POST `/api/v1/auth/register` (debug-mode only)
2. **Login / logout** — JWT access + refresh cycle with httpOnly cookie
3. **MFA setup + verify + disable** — TOTP counter-based verification works
4. **Agent enrollment** — POST `/api/v1/agent/v1/register` with enrollment-token
5. **Heartbeat** — Updates last_seen/last_heartbeat, stores health_data
6. **Process telemetry ingestion** — Field sanitization, hash extraction, datetime parse
7. **Service telemetry ingestion** — Account mapping, hash extraction
8. **Startup inventory ingestion** — Source enum, extra-field pruning
9. **EventLog ingestion** — Channel→source rename, extracted dict merge
10. **Process list API** — Snapshot-window latest-record fetch with staleness flag
11. **Service list API** — Same snapshot-window approach
12. **EventLog list API** — Full filter support with provider_name extraction
13. **Alert triage / resolve** — Status transition with audit trail
14. **Bulk triage** — Multi-alert batch update
15. **Alert evidence retrieval** — By alert_id lookup
16. **Rule CRUD** — Custom rules persisted to DB; promote/demote workflows
17. **Built-in rule listing** — ALL_RULES export with MITRE mapping
18. **Audit log query** — Actor/action/resource filters with CSV export
19. **Report generation** — Alert stats + endpoint breakdown + investigation export
20. **Dark/light theme** — Zustand persist store with CSS variable toggle

---

## 10. Summary Verdict

| Dimension | Rating | Comment |
|-----------|--------|---------|
| Architecture coherence | 🟢 Strong | Clear separation of agent/backend/frontend; config hierarchy consistent |
| Security posture | 🟡 Moderate | Good intent (mTLS, JWT, Argon2) but execution gaps (hardcoded fallback, static signatures) |
| Detection engine | 🔴 Incomplete | Rule model rich; evaluation logic is a no-op (`return False`) |
| Alert pipeline | 🔴 Broken | Ingestion works; creation from detection is `alerts_created = 0` placeholder |
| AI investigation | 🟡 Functional | Endpoints exist; requires live Ollama + qwen3.5:4b model |
| Frontend completeness | 🟡 Moderate | Core CRUD UIs done; 4 pages partially stubbed or dead-ended |
| Test coverage | 🔴 Weak | <5%; zero E2E |
| Migration readiness | 🔴 Blocked | No Alembic; schema drift risk high |

**Overall**: ~60% feature-complete for a development/local environment. Production-readiness gates at: (1) fix critical syntax errors, (2) implement real detection evaluation, (3) add database migrations, (4) raise test coverage to ≥40%, (5) close security gaps around hardcoded secrets.
