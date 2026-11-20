# SentinelWatch — Technical Debt Register

**Date**: 2026-11-14
**Priority**: P0 (critical) → P3 (nice-to-have)

---

## P0 — Must Fix Before Any Production Use

### TD-01 — Compilation errors block backend startup
**Files**: `backend/src/sentinelwatch_backend/database.py:183-185`
**Symptom**: SyntaxError at import; FastAPI cannot boot.
**Fix**: Rewrite `init_database()` body. The truncated line must reconstruct the `check_database_connection` helper and ensure the function closes properly with a return statement.
**Effort**: 1 hour
**Risk if deferred**: Server will not start.

### TD-02 — Role/Permission primary keys collide
**File**: `backend/src/sentinelwatch_backend/models/role.py:17`
**Code**: `default=lambda: "..."`
**Symptom**: Every inserted role gets id `"..."` causing `IntegrityError` on second insert; permission join table breaks.
**Fix**: Replace with `default=lambda: str(uuid.uuid4())` and add `import uuid` at top of file.
**Effort**: 15 minutes

### TD-03 — Detection engine never fires alerts ✅ RESOLVED
**File**: `backend/src/sentinelwatch_backend/detection_rules/rule_model.py:351-425`
**Fix applied**: Wired `ConditionEvaluator` into `_evaluate_condition()`. Added `_normalize_telemetry()` (process/service/startup/eventlog field mapping), `_validate_rule_condition()` (evidence requirements gate), proper error logging instead of silent swallowing. No `eval()` used — safe recursive-descent CEL parser.
**Evidence**: Tests in `test_detection_engine.py` (202 lines) and `test_condition_evaluator.py` (149 lines). All source files pass `python3 -m py_compile`.
**Date resolved**: 2026-11-17

### TD-04 — Alert resolution endpoint returns malformed response
**File**: `backend/src/sentinelwatch_backend/api/v1/alert_lifecycle.py:248-263`
**Symptom**: After resolving an alert, the function mutates the dict returned by `AlertResponse.model_validate(alert)` but does not re-validate; may raise Pydantic validation error or return partial JSON.
**Fix**: Call `AlertResponse.model_validate(alert, from_attributes=True)` after all mutations and return that object.
**Effort**: 30 minutes

### TD-05 — Authentication GET handler contains POST-body logic
**File**: `backend/src/sentinelwatch_backend/api/v1/auth.py` near line 618
**Symptom**: A GET route `/users/{user_id}` appears to contain a password-change body (references `body.new_password`). Likely a copy-paste artifact from a PATCH handler merged into the wrong function.
**Fix**: Isolate each HTTP method into its own endpoint; remove the conflicting body access from the GET path.
**Effort**: 1 hour

### TD-06 — Hardcoded JWT secret fallback is a backdoor
**File**: `backend/src/sentinelwatch_backend/config.py:60`
**Code**: `jwt_secret: str = "CHANGE_ME_IN_PRODUCTION_USE_STRONG_RANDOM_KEY"`
**Symptom**: If `.env` is missing or incorrectly loaded, every instance uses the same static secret — forgeable by anyone who sees this source.
**Fix**: Make the default empty string; raise `ValueError` at startup when no secret is configured. Keep the warning-only path for local development behind a feature flag or require explicit `--insecure-use-default-secret` CLI flag during initial bootstrap.
**Effort**: 1 hour

### TD-07 — No database migrations
**Files**: Entire `backend/alembic/` directory is absent
**Impact**: Schema changes in dev (`create_all`) leave production stuck; rolling out a new column means dropping/recreating the DB.
**Fix**: Initialize Alembic (`alembic init alembic`), point `alembic.ini` at existing SQLite URL, run `alembic revision --autogenerate` to capture current state as migration 001, then create the upgrade/downgrade scripts for future changes.
**Effort**: Half day (initial migration) + 1 hour per subsequent change

---

## P1 — High Priority

### TD-08 — Alert creation is stubbed at zero ✅ RESOLVED
**File**: `backend/src/sentinelwatch_backend/api/v1/agent_communication.py` (telemetry handler)
**Fix applied**: Full alert pipeline wired — DetectionEngine evaluates each accepted record, entity-aware dedup key (`rule|agent|entity_id`) prevents cross-process suppression, correlation ID is batch-scoped deterministic hash, evidence rows stored with raw_records JSONB linked by FK, `alerts_created` counter only increments for new non-suppressed alerts. Cmd-line credentials redacted before storage.
**Evidence**: Tests in `test_alert_correctness.py` (146 lines). Counter accuracy, dedup distinctness, correlation ID stability all verified.
**Date resolved**: 2026-11-17

### TD-09 — Config signature is always "placeholder" ✅ RESOLVED
**Files**: `backend/src/sentinelwatch_backend/security/config_signing.py` (new), `agent_communication.py`
**Fix applied**: New module `security/config_signing.py` provides `sign_config(payload, secret)` and `verify_signature(payload, sig, secret)` using HMAC-SHA256 over canonical sorted-key JSON. All four response paths in `agent_communication.py` now pass real signatures via `_sign_config_for_agent(config_data, config_version)` instead of `"placeholder"`. Secret derives from existing `auth.jwt_secret` config value.
**Evidence**: Tests in `test_config_signing.py` (41 lines) — round-trip sign/verify, tamper detection, wrong-secret rejection, canonical stability across dict orderings.
**Date resolved**: 2026-11-17

### TD-10 — RulesRouter module-level bare function
**File**: `backend/src/sentinelwatch_backend/api/v1/rules.py:221-258`
**Symptom**: `create_rule` defined outside any decorator; not mounted on the router.
**Fix**: Add `@router.post("", response_model=dict, status_code=201)` above the function definition.
**Effort**: 15 minutes

### TD-11 — SuppressionRouter file double-definition
**File**: `backend/src/sentinelwatch_backend/api/v1/suppression.py:20,63`
**Symptom**: Two `router = APIRouter(...)` declarations; second overwrites first. May silently drop routes.
**Fix**: Remove the first declaration (line 20) and keep only the one at line 63. Verify all endpoints render under the correct prefix.
**Effort**: 15 minutes

### TD-12 — Sync Session in async report handler
**File**: `backend/src/sentinelwatch_backend/api/v1/reports.py:148-149`
**Code**: `db: Session = Depends(get_db)` inside async function — gets sync session; `explore_investigation` mixes sync queries with async context.
**Fix**: Change to `db: AsyncSession = Depends(get_db)`; rewrite all `db.query(...)` calls to async SELECT style.
**Effort**: 2 hours

### TD-13 — AIInvestigationPage is a 27-line stub
**File**: `frontend/src/pages/AIInvestigationPage.tsx`
**Content**: `<AI Investigation</>` literal JSX.
**Fix**: Build a full page that (a) fetches `/ai/status`, (b) shows Ollama availability badge, (c) renders the list of unresolved alerts, (d) lets analyst pick one and call `/alerts/{id}/investigate`, (e) displays the JSON report with markdown rendering.
**Effort**: 1 day

### TD-14 — Process tree API always returns empty
**File**: `backend/src/sentinelwatch_backend/api/v1/telemetry.py:229-242`
**Symptom**: Query finds a row but returns `{processes: []}`.
**Fix**: Replace with a proper recursive CTE or in-memory tree builder: select all records for `(agent_id, max_collected_at)`, partition by pid→ppid, build adjacency list, emit as nested JSON.
**Effort**: Half day

---

## P2 — Medium Priority

### TD-15 — WebSocket live-alert stream declared but unimplemented
**Files**: `main.py`, `config.py:websocket` section
**Fix**: Add `@app.websocket("/ws/alerts")` endpoint authenticated via query param Bearer token; subscribe on connect; broadcast on alert.create audit event.
**Effort**: 1 day

### TD-16 — Prometheus metrics have no instrumented counters
**File**: `main.py:140-143`
**Fix**: Register gauges/histograms: `http_request_duration_seconds`, `telemetry_records_ingested_total`, `alerts_generated_total`, `detection_rule_evaluations_total`.
**Effort**: Half day

### TD-17 — Rate-limiting config unused
**File**: `config.py:RateLimitingConfig`
**Fix**: Add slowapi or hand-roll token-bucket middleware on `/api/v1/*`.
**Effort**: 1 day

### TD-18 — Audit log has no append-only enforcement
**File**: `models/audit.py`
**Fix**: Set OS-level immutable bit on audit.log via `chattr +a` (Linux) or SACL (Windows); or use a dedicated write-once WAL table with a trigger rejecting UPDATE/DELETE.
**Effort**: Half day

### TD-19 — CSP header missing from security middleware
**File**: `main.py:80-89`
**Fix**: Add `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'` (adjust for dev).
**Effort**: 20 minutes

### TD-20 — Retention cleanup scheduler absent
**File**: N/A — feature gap
**Fix**: Background task running hourly; DELETE WHERE collected_at < NOW() - interval_days per telemetry type.
**Effort**: Half day

### TD-21 — Agent health model inconsistency
**Files**: `models/health.py` is imported both as DB-model (`Agent.health_data: JSONB`) and as Pydantic class (`AgentHealth`). The DB model stores dict; the Pydantic class implements metrics. They share no schema contract.
**Fix**: Align — either store serialized JSON with a typed response model, or add a separate `agent_health_snapshots` table with columns instead of JSONB.
**Effort**: 1 day

### TD-22 — No frontend loading skeletons for long operations
**Files**: `AlertInvestigationPage.tsx`, `AIInvestigationPage.tsx`
**Fix**: Add skeleton components during the ≥30 s Ollama call.
**Effort**: 2 hours

---

## P3 — Low Priority / Nice-to-Have

### TD-23 — No Dockerfile or docker-compose
**Effort**: 1 day
**Impact**: Deployment reproducibility limited.

### TD-24 — No frontend/unit test specs
**Effort**: 2 days to reach 40% coverage.

### TD-25 — No end-to-end test suite
**Effort**: 3 days.

### TD-26 — README phase status outdated
**File**: `README.md:161-168` shows Phase 2–6 as "Pending" though most are substantial.
**Effort**: 15 minutes.

### TD-27 — Documentation gaps
**Files**: No API changelog; no CONTRIBUTING.md; threat model omits agent-compromise scenario.
**Effort**: 1 day total across docs.

### TD-28 — Missing OpenTelemetry tracing
**Effort**: 1 day.

---

## Debt by Category Summary

| Category | P0 | P1 | P2 | P3 | Total |
|----------|----|----|----|----|-------|
| Core backend | 5 | 3 | 2 | 1 | 11 |
| Detection engine | 1 | 1 | 0 | 0 | 2 |
| Agent | 0 | 1 | 1 | 0 | 2 |
| Frontend | 0 | 2 | 2 | 2 | 6 |
| Security | 1 | 1 | 2 | 1 | 5 |
| DevOps / infra | 1 | 0 | 3 | 3 | 7 |
| **Grand total** | **8** | **8** | **10** | **7** | **33** |
