# SentinelWatch — Project Completion Roadmap

**Date**: 2026-11-14
**Scope**: From current state to GitHub-ready, production-capable platform
**Approach**: Sequential phases; each phase must pass verification before the next begins.

---

## Guiding Principles

1. **Fix what's broken before adding features.** P0 debt items block core functionality.
2. **One task at a time.** Each item has a clear done/undone boundary.
3. **Verification gates.** No phase ships without tests covering its changed paths.
4. **Zero mock telemetry in production dashboards.** Real data only.
5. **AI explains evidence, never guesses.** All AI outputs reference attached record IDs.

---

## Phase 0 — Repository Audit ✅ (this task)

Deliverables completed:
- [x] `PROJECT_AUDIT.md`
- [x] `FEATURE_IMPLEMENTATION_MATRIX.md`
- [x] `TECHNICAL_DEBT.md`
- [x] `PROJECT_COMPLETION_ROADMAP.md` (this document)

---

## Phase 1 — Stabilize Core Backend (P0 fixes)

**Objective**: Backend starts, serves requests, persists data correctly.

| Task | Description | Est. | Files |
|------|-------------|------|-------|
| 1.1 | Fix `database.py` syntax error | 1h | `database.py` |
| 1.2 | Fix Role.id `lambda:"..."` → uuid4 | 15m | `models/role.py` |
| 1.3 | Fix alert.resolve response mutation | 30m | `api/v1/alert_lifecycle.py` |
| 1.4 | Separate GET /users/{id} from PATCH body | 1h | `api/v1/auth.py` |
| 1.5 | Hard-code secret fallback → strict fail at startup | 1h | `config.py` |
| 1.6 | Initialize Alembic, generate first migration | 3h | `backend/alembic/` |
| 1.7 | Fix `create_rule` missing `@router.post` decorator | 15m | `api/v1/rules.py` |
| 1.8 | Remove duplicate `router=` in suppression.py | 15m | `api/v1/suppression.py` |
| 1.9 | Fix reports.py async/sync session mismatch | 2h | `api/v1/reports.py` |
| 1.10 | Verify all routers mount cleanly (`python -c "from sentinelwatch_backend.main import create_app; app = create_app()"`) | 1h | — |

**Gate**: `pytest backend/tests` passes; `curl http://127.0.0.1:8001/health` returns 200; `curl /docs` loads.

---

## Phase 2 — Implement Detection Engine (P0 + P1)

**Objective**: Real telemetry evaluated against rules produces real alerts.

| Task | Description | Est. | Files |
|------|-------------|------|-------|
| 2.1 | Write condition evaluator — support regex match, equality, membership, boolean ops, numeric comparison | 1d | `detection_rules/evaluator.py` |
| 2.2 | Flatten telemetry record (ProcessTelemetry row) into flat dict matching rule field names | 2h | `detection_rules/evaluator.py` |
| 2.3 | Integrate evaluator into `rule_model.DetectionEngine.evaluate()` | 2h | `detection_rules/rule_model.py` |
| 2.4 | Wire `submit_telemetry` to run evaluation per accepted record | 3h | `api/v1/agent_communication.py` |
| 2.5 | Persist generated Alert + Evidence rows in same transaction | 2h | `api/v1/agent_communication.py`, `models/alert.py` |
| 2.6 | Deduplication: skip alert if same rule+agent+effectively-same-telemetry within dedup_window | 3h | `detection_rules/rule_model.py` |
| 2.7 | Add integration tests: each of the 23 built-in rules exercised against synthetic telemetry | 2d | `backend/tests/test_detection.py` |
| 2.8 | Benchmark: measure avg eval time per rule; cap at < 1 ms | 1h | `detection_rules/rule_model.py` |

**Gate**: Run agent locally sending real process telemetry; confirm alerts appear in `/api/v1/alerts` matching expected rules.

---

## Phase 3 — Fix Alert Pipeline

**Objective**: Alerts triage, resolve, note, and evidence flows work end-to-end.

| Task | Description | Est. | Files |
|------|-------------|------|-------|
| 3.1 | Complete alert_triage PATCH body (validate enum, write audit entry) | 2h | `alert_lifecycle.py` |
| 3.2 | Complete alert_resolve PATCH body (same as 3.1) | 2h | `alert_lifecycle.py` |
| 3.3 | Add bulk-decline endpoint (`POST /alerts/bulk/resolve`) | 2h | `alert_lifecycle.py` |
| 3.4 | Attach Evidence row at alert creation time (snapshot of triggering telemetry) | 3h | `agent_communication.py` |
| 3.5 | Add `GET /alerts/{id}/related` — fetch sibling telemetry within 30 min window | 2h | `alert_lifecycle.py` |
| 3.6 | Frontend: wire AlertInvestigationPage to call related-telemetry endpoint | 2h | `pages/AlertInvestigationPage.tsx` |

**Gate**: Full lifecycle test: ingest → detect → alert created → triage → resolve → audit logged.

---

## Phase 4 — Security Hardening

**Objective**: Close all P0 security findings and add critical headers.

| Task | Description | Est. | Files |
|------|-------------|------|-------|
| 4.1 | Implement Ed25519 config-signing keypair generator + config-sign endpoint | 1d | `crypto/certificates.py`, `agent_communication.py` |
| 4.2 | Agent-side config signature verification before apply | 3h | `main.py:_on_config_received` |
| 4.3 | Add CSP header to security middleware | 20m | `main.py:security_headers` |
| 4.4 | Harden JWT: reject tokens issued before password change (already present; add regression test) | 1h | `api/v1/auth.py`, `tests/test_auth.py` |
| 4.5 | Add brute-force lockout duration config + admin-unlock endpoint | 2h | `auth.py`, `api/v1/auth.py` |
| 4.6 | Ensure audit.log has restricted permissions on both Windows and Unix | 1h | `logging.py` setup code |
| 4.7 | Review and harden CORS defaults; reject wildcard origins in non-debug mode | 1h | `config.py` |

**Gate**: Run Bandit + safety scan; zero high-severity findings. Update `TOKEN_SECURITY_ARCHITECTURE.md` if new findings emerge.

---

## Phase 5 — Frontend Completion

**Objective**: All pages functional; no stubs.

| Task | Description | Est. | Files |
|------|-------------|------|-------|
| 5.1 | Build full AIInvestigationPage: Ollama status badge, alert picker, result renderer | 1d | `pages/AIInvestigationPage.tsx` |
| 5.2 | Implement real process-tree query (CTE or in-memory aggregation) | 1d | `telemetry.py:229`, `ProcessExplorerPage.tsx` |
| 5.3 | Add loading skeletons to AlertInvestigation and AIInvestigation pages | 2h | Both pages |
| 5.4 | Add WebSocket subscription on DashboardPage for live alert count badge | 1d | `DashboardPage.tsx`, `main.py` WebSocket handler |
| 5.5 | Fix SettingsPage MFA-disable flow | 1h | `pages/SettingsPage.tsx` |
| 5.6 | Add 404 and unauthorized fallback routes | 1h | `App.tsx` |

**Gate**: Smoke-test each page in browser; keyboard navigation; dark/light toggle on every page.

---

## Phase 6 — Additional Features (P1/P2 from tech debt)

| Task | Description | Est. | Files |
|------|-------------|------|-------|
| 6.1 | WebSocket `/ws/alerts` endpoint with Bearer query-param auth | 1d | `main.py`, `api/v1/websockets.py` (new) |
| 6.2 | Prometheus instrumentation: request counter, latency histogram, telemetry gauge | 1d | `metrics.py` (new), `main.py` |
| 6.3 | Rate-limiting middleware (slowapi or custom token bucket) | 1d | `middleware/rate_limit.py` (new) |
| 6.4 | Retention cleanup background task (APScheduler or FastAPI lifespan task) | 1d | `tasks/retention_cleanup.py` (new) |
| 6.5 | Agent health snapshots table (replace JSONB with typed columns) | 1d | `models/health.py`, migration |
| 6.6 | Add SuppressionRule to detection evaluation loop | 2d | `detection_rules/rule_model.py`, `api/v1/suppression.py` |
| 6.7 | EventLog correlation rules (CR-001, CR-002) — implement actual SQL temporal joins | 2d | `detection_rules/correlation_rules.py` (new) |

---

## Phase 7 — Test Suite

**Objective**: ≥ 60% coverage on backend, 40% on frontend.

| Task | Description | Est. | Files |
|------|-------------|------|-------|
| 7.1 | Backend API tests — login, register, CRUD on agents/alerts/rules | 2d | `backend/tests/test_api_*.py` |
| 7.2 | Backend detection tests — synthesize telemetry, assert rule matches | 2d | `backend/tests/test_detection.py` |
| 7.3 | Backend auth tests — token rotation, MFA, password change invalidation | 1d | `backend/tests/test_auth.py` |
| 7.4 | Frontend unit tests — AuthStore actions, API helper wrappers, page render | 2d | `frontend/src/**/*.test.tsx` |
| 7.5 | E2E test — spin up backend + frontend dev server, register agent, submit telemetry, observe alert | 3d | `tests/e2e/` |
| 7.6 | Add pre-commit hooks: ruff, mypy, bandit, pytest | 1d | `.pre-commit-config.yaml` |

**Gate**: `pytest --cov=src/sentinelwatch_backend` reports ≥ 60%; `npm run test:run` reports ≥ 40%.

---

## Phase 8 — Documentation & Packaging

| Task | Description | Est. | Files |
|------|-------------|------|-------|
| 8.1 | Update README phase table to reflect actual progress | 30m | `README.md` |
| 8.2 | Add CONTRIBUTING.md with dev setup steps | 1h | `CONTRIBUTING.md` |
| 8.3 | Add CODE_OF_CONDUCT.md (Contributor Covenant) | 30m | `CODE_OF_CONDUCT.md` |
| 8.4 | Add API changelog (`docs/CHANGELOG.md`) capturing current version milestones | 1h | `docs/CHANGELOG.md` |
| 8.5 | Expand threat model to cover agent compromise, insider analyst, config tampering | 1d | `docs/threat-model.md` |
| 8.6 | Generate Postman collection from OpenAPI spec | 2h | `scripts/generate-postman.py` |
| 8.7 | Draft `docker-compose.yml` (backend + sqlite volume) | 1d | `docker-compose.yml` |
| 8.8 | Final GitHub repo cleanup: remove .env, __pycache__, venv references from gitignore sanity check | 1h | `.gitignore` verification |

---

## Phase 9 — Final Verification & Release Prep

| Task | Description | Est. | Files |
|------|-------------|------|-------|
| 9.1 | Full integration run on clean Windows VM: install → enroll → collect → detect → alert → triage → investigate | 1d | Manual |
| 9.2 | Load test: 50 agents streaming at 30s interval for 1 hour; verify no memory leak | 1d | Scripts |
| 9.3 | Security review: Bandit + safety + manual pen-test of auth endpoints | 1d | Automated + manual |
| 9.4 | Draft v1.0.0 release tag; run `.github/workflows/release.yml` end-to-end | 2h | CI |
| 9.5 | Record 3-minute demo video (screen capture) showing full flow | 2h | Asset |
| 9.6 | Populate GitHub Releases page with `SentinelWatch-v1.0.0-windows.zip` | 30m | GitHub UI |

---

## Effort Estimate Summary

| Phase | Tasks | Est. Person-Days |
|-------|-------|-----------------|
| 0 — Audit (done) | 4 docs | 0.5 |
| 1 — Stabilize | 10 | 8 |
| 2 — Detection engine | 8 | 9 |
| 3 — Alert pipeline | 6 | 3.5 |
| 4 — Security | 7 | 4 |
| 5 — Frontend | 6 | 4 |
| 6 — Additional features | 7 | 9 |
| 7 — Tests | 6 | 10 |
| 8 — Docs & packaging | 8 | 4.5 |
| 9 — Final verification | 5 | 4 |
| **Total** | **65 tasks** | **~56 person-days** |

---

## Unresolved Limitations (Known at Audit Time)

These require architectural decisions beyond this audit:

1. **PostgreSQL readiness**: Backend code targets PostgreSQL dialect (`JSONB`, `asyncpg` extra) but SQLite is the default. Mixing both requires connection-dialect guards throughout all queries. Currently untested.
2. **Windows EventLog access**: `win32evtlog` module requires elevated privileges for some channels; agent runs as standard user by default. Limited coverage for SYSTEM channel events.
3. **Multi-agent scale**: Single-server SQLite backend has not been load-tested beyond ~5 concurrent agents. Horizontal scaling requires PostgreSQL + message queue redesign.
4. **Cross-platform agent**: `win32*` imports make the agent Windows-only. Linux/macOS variants are not planned.
5. **AI provider lock-in**: Current AI investigation supports Ollama only. Extending to OpenAI/Claude API requires a provider abstraction layer not yet designed.
