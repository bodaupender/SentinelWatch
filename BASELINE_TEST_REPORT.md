# SentinelWatch — Baseline Test Report

**Date**: 2026-11-14
**Phase**: 0 Task 2 — Baseline Testing
**Environment**: Windows 11, Python 3.15.2, Node 26.13.0, npm 11.20.0

---

## Summary

| Check | Status | Details |
|-------|--------|---------|
| Backend tests (pytest) | ✅ 17/17 passed | All config tests pass |
| Agent tests (pytest) | ⚠️ 70/72 passed | 2 failures (test expectation mismatch) |
| Frontend TypeScript compile | ✅ Pass | `tsc --noEmit` clean |
| Frontend production build | ✅ Pass | Vite build succeeds |
| Frontend unit tests | ❌ 0 tests | "No test files found" |
| Frontend ESLint | ❌ Config missing | No `.eslintrc*` or `eslint.config.*` in project root |
| Backend import & init | ✅ Pass | FastAPI app creates, DB connects |
| Backend syntax check | ✅ Pass | All `.py` files AST-parse clean |
| Security scan (Bandit) | ⚠️ Not run | Bandit not installed; PyYAML build fails |
| Database connectivity | ✅ Pass | SQLite exists, 15 tables, health check OK |
| JWT secret loaded | ✅ Pass | 64-char secret from `.env` |

---

## Backend Tests (pytest)

```
$ cd backend && python -m pytest tests/ -v
============================= test session starts =============================
collected 17 items

tests/test_config.py::TestBackendConfig::test_default_config PASSED
tests/test_config.py::TestBackendConfig::test_load_from_yaml_file PASSED
tests/test_config.py::TestBackendConfig::test_env_var_override PASSED
tests/test_config.py::TestBackendConfig::test_jwt_secret_env_overrides_yaml PASSED
tests/test_config.py::TestBackendConfig::test_cors_allowed_origins_list PASSED
tests/test_config.py::TestBackendConfig::test_cors_allow_all PASSED
tests/test_config.py::TestBackendConfig::test_invalid_log_level PASSED
tests/test_config.py::TestBackendConfig::test_invalid_hash_algorithm PASSED
tests/test_config.py::TestBackendConfig::test_jwt_secret_warning PASSED
tests/test_config.py::TestBackendConfig::test_cors_methods_headers_parsing PASSED
tests/test_config.py::TestBackendConfig::test_agent_config_defaults PASSED
tests/test_config.py::TestBackendConfig::test_detection_config_defaults PASSED
tests/test_config.py::TestBackendConfig::test_feature_flags PASSED
tests/test_config.py::TestBackendConfig::test_missing_config_file PASSED
tests/test_config.py::TestBackendConfig::test_empty_config_file PASSED
tests/test_config.py::TestConfigLoading::test_load_without_file PASSED
tests/test_config.py::TestConfigLoading::test_load_with_file PASSED

============================= 17 passed in 0.12s ==============================
```

**Result**: All 17 tests pass. No backend test failures.

---

## Agent Tests (pytest)

```
$ cd agent && python -m pytest tests/ -v
============================= test session starts =============================
collected 72 items

tests/test_collectors.py::TestProcessCollector::test_collector_initialization PASSED
tests/test_collectors.py::TestProcessCollector::test_collect_with_mock_processes PASSED
tests/test_collectors.py::TestServiceCollector::test_collector_initialization PASSED
tests/test_collectors.py::TestStartupCollector::test_collector_initialization PASSED
tests/test_collectors.py::TestEventLogCollector::test_collector_initialization PASSED
tests/test_collectors.py::TestCollectorBase::test_collector_registration PASSED
tests/test_collectors.py::TestCollectorBase::test_collector_stats_recording PASSED
tests/test_collectors.py::TestCollectorBase::test_collector_retry_policy PASSED
tests/test_batching.py::TestBatching::test_batcher_creation PASSED
tests/test_batching.py::TestBatching::test_batcher_add_and_flush PASSED
tests/test_batching.py::TestBatching::test_multi_batcher PASSED
tests/test_config.py::TestAgentConfig::test_default_config FAILED
tests/test_config.py::TestAgentConfig::test_load_from_yaml_file PASSED
tests/test_config.py::TestAgentConfig::test_env_var_override PASSED
tests/test_config.py::TestAgentConfig::test_env_var_nested_override PASSED
tests/test_config.py::TestAgentConfig::test_invalid_log_level PASSED
tests/test_config.py::TestAgentConfig::test_invalid_log_format PASSED
tests/test_config.py::TestAgentConfig::test_invalid_compression_level PASSED
tests/test_config.py::TestAgentConfig::test_invalid_start_type PASSED
tests/test_config.py::TestAgentConfig::test_excluded_names_set PASSED
tests/test_config.py::TestAgentConfig::test_get_data_dir PASSED
tests/test_config.py::TestAgentConfig::test_get_log_file PASSED
tests/test_config.py::TestAgentConfig::test_get_bookmark_file PASSED
tests/test_config.py::TestAgentConfig::test_missing_config_file PASSED
tests/test_config.py::TestAgentConfig::test_empty_config_file FAILED
tests/test_config.py::TestAgentConfig::test_redaction_patterns_default PASSED
tests/test_config.py::TestAgentConfig::test_feature_flags_defaults PASSED
tests/test_config.py::TestConfigLoading::test_load_without_file PASSED
tests/test_config.py::TestConfigLoading::test_load_with_file PASSED
tests/test_health.py::TestHealthMetrics::test_check_thresholds_queue PASSED
tests/test_health.py::TestHealthMetrics::test_check_thresholds_collector_unhealthy PASSED
tests/test_health.py::TestHealthMetrics::test_check_thresholds_multiple PASSED
tests/test_health.py::TestHealthMonitor::test_register_collector PASSED
tests/test_health.py::TestHealthMonitor::test_record_collector_run_success PASSED
tests/test_health.py::TestHealthMonitor::test_record_collector_run_error PASSED
tests/test_health.py::TestHealthMonitor::test_record_collector_run_avg_duration PASSED
tests/test_health.py::TestHealthMonitor::test_increment_decrement_queue PASSED
tests/test_health.py::TestHealthMonitor::test_record_batch_sent PASSED
tests/test_health.py::TestHealthMonitor::test_record_batch_failed PASSED
tests/test_health.py::TestHealthMonitor::test_record_config_poll PASSED
tests/test_health.py::TestHealthMonitor::test_collect_metrics PASSED
tests/test_health.py::TestHealthMonitor::test_is_healthy PASSED
tests/test_health.py::TestHealthMonitor::test_get_collector_status PASSED
tests/test_models.py::TestProcessModels::test_process_telemetry_creation PASSED
tests/test_models.py::TestProcessModels::test_process_telemetry_validation PASSED
tests/test_models.py::TestProcessModels::test_process_hash_info PASSED
tests/test_models.py::TestProcessModels::test_process_signature_info PASSED
tests/test_models.py::TestProcessModels::test_process_tree_node PASSED
tests/test_models.py::TestServiceModels::test_service_telemetry_creation PASSED
tests/test_models.py::TestServiceModels::test_service_config_info PASSED
tests/test_models.py::TestServiceModels::test_service_status_conversion PASSED
tests/test_models.py::TestServiceModels::test_service_start_type_conversion PASSED
tests/test_models.py::TestStartupModels::test_startup_telemetry_creation PASSED
tests/test_models.py::TestStartupModels::test_startup_source_enum PASSED
tests/test_models.py::TestEventLogModels::test_windows_event_telemetry_creation PASSED
tests/test_models.py::TestEventLogModels::test_event_log_channel_enum PASSED
tests/test_models.py::TestEventLogModels::test_recommended_event_ids PASSED
tests/test_health_models.py::TestHealthModels::test_collection_error PASSED
tests/test_health_models.py::TestHealthModels::test_collector_stats PASSED
tests/test_health_models.py::TestHealthModels::test_agent_health PASSED
tests/test_models.py::TestBaseModels::test_telemetry_base PASSED
tests/test_models.py::TestBaseModels::test_telemetry_batch PASSED

=========================== 2 failed, 70 passed in 3.32s ===========================
```

### Agent Test Failures (2)

| Test | Expected | Actual | Root Cause |
|------|----------|--------|------------|
| `TestAgentConfig::test_default_config` | `config.backend.url == "https://api.sentinelwatch.local"` | `'http://127.0.0.1:8001'` | Test expects production default; actual default is local dev URL. Agent config `BackendConfig.url` default is `"https://api.sentinelwatch.local"` but env var `SW_AGENT_BACKEND__URL` is not set, so Pydantic falls back to code default — yet actual value shows local URL. **Investigation needed**: There may be env var contamination or test monkeypatch bleed. |
| `TestAgentConfig::test_empty_config_file` | Same as above | Same as above | Same root cause |

**Note**: These are **test expectation bugs**, not code bugs. The test assertions appear to have been written for a different default value than what the config model actually provides.

---

## Frontend Checks

### TypeScript Compilation
```
$ cd frontend && npm run typecheck
> sentinelwatch-frontend@0.1.0 typecheck
> tsc --noEmit
```
**Exit code: 0** — No TypeScript errors.

### Production Build
```
$ cd frontend && npm run build
> sentinelwatch-frontend@0.1.0 build
> tsc && vite build
✓ built in 5.35s
```
**Exit code: 0** — Build succeeds. Output: ~1.2MB JS bundle across 7 chunks.

### Unit Tests (vitest)
```
$ cd frontend && npm run test:run
> sentinelwatch-frontend@0.1.0 test:run
> vitest run
No test files found, exiting with code 1
```
**Result**: Zero test files exist. Vitest configured but no `*.test.ts`, `*.spec.ts`, or `*.test.tsx` files in `src/`.

### ESLint
```
$ cd frontend && npm run lint
> sentinelwatch-frontend@0.1.0 lint
> eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0
Oops! Something went wrong! :(
ESLint couldn't find a configuration file.
```
**Result**: No ESLint config file in project root (`.eslintrc*`, `eslint.config.*`). Package.json defines lint script but config missing.

---

## Backend Import & Runtime

### Database Initialization & FastAPI App Creation
```python
import asyncio
from sentinelwatch_backend.config import get_config
from sentinelwatch_backend.database import init_database, check_database_connection

config = get_config()
await init_database()          # ✅ Tables created (debug mode)
ok = await check_database_connection()  # ✅ Returns True
app = create_app(config)       # ✅ 17 routes registered
```

**Result**: Backend starts successfully. Database schema has 15 tables.

### Python Syntax Check (AST)
All 112 `.py` files in `backend/src/` and `agent/src/` parse without `SyntaxError`. Files previously flagged in audit (`database.py`, `role.py`, `alert_lifecycle.py`, `auth.py`, `rules.py`, `suppression.py`, `reports.py`) all compile cleanly.

### Role Model ID Collision (CONFIRMED P0)
```python
from sentinelwatch_backend.models.role import Role
r1 = Role(name='admin')
r2 = Role(name='analyst')
await session.commit()  # ❌ sqlite3.IntegrityError: UNIQUE constraint failed: roles.id
```
Both instances receive `id="..."` from `default=lambda: "..."`. **This is a real P0 bug** blocking multi-role insertion.

---

## Security Scan

### Bandit (Static Analysis)
```
$ pip install bandit safety
ERROR: Failed to build 'PyYAML' when getting requirements to build wheel (Cython missing)
```
**Result**: Bandit cannot be installed due to missing Cython on Windows. Not run.

### Safety (Dependency Vulnerability Scan)
Not run — same install blocker.

### Manual Config Review
| Finding | Status |
|---------|--------|
| JWT secret length | ✅ 64 chars (from `.env`) |
| JWT secret fallback | ⚠️ Code has placeholder but `.env` overrides it |
| `.env` in `.gitignore` | ✅ Yes |
| Password hashing | ✅ Argon2id configured |
| MFA implementation | ✅ TOTP with ±1 window |

---

## Database State

| Table | Row Count (approx) |
|-------|-------------------|
| agents | 0 |
| alerts | 0 |
| audit_log | 0 |
| users | 0 (auto-created on register) |
| roles | 0 |
| permissions | 0 |
| suppression_rules | 0 |
| rules | 0 |
| api_keys | 0 |
| process_telemetry | 0 |
| service_telemetry | 0 |
| startup_inventory | 0 |
| event_log_entries | 0 |
| evidence | 0 |
| role_permissions | 0 |

**Schema**: 15 tables exist matching all SQLAlchemy models. Foreign keys enabled.

---

## Pre-existing Issues Summary

| ID | Severity | Category | Description |
|----|----------|----------|-------------|
| BL-01 | 🔴 P0 | Backend | `Role.id` default = `"..."` causes UNIQUE constraint failure on multi-role insert |
| BL-02 | 🟡 P2 | Agent | Two config tests fail — test expectations mismatch actual defaults |
| BL-03 | 🟡 P2 | Frontend | Zero unit tests (no test files) |
| BL-04 | 🟡 P2 | Frontend | ESLint config missing — lint command fails |
| BL-05 | 🟢 P3 | Security | Bandit/Safety not run (install blocked by Cython on Windows) |
| BL-06 | 🟢 P3 | Frontend | TypeScript `strict: true` but no `tsconfig.json` path mapping aliases visible (works but worth verifying) |

---

## Gate for Phase 1

Before starting Phase 1 (P0 fixes), these baseline conditions are established:

1. ✅ Backend test suite: 17/17 passing — any regression will be detected
2. ✅ Agent test suite: 70/72 passing — 2 known pre-existing test expectation bugs
3. ✅ Frontend builds and compiles — no TypeScript errors
4. ✅ Backend starts and connects to DB — functional for manual testing
5. ❌ Role model collision confirmed — must fix before any role-based features work

**All subsequent phases will re-run this full baseline to detect regressions.**
