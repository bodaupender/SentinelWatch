# SentinelWatch Project — Phase 1 Engineering Foundation Report

## Objective

Establish a maintainable, secure, reliable engineering foundation without unnecessarily rebuilding working code. Only fix foundational problems identified by the verified Phase 0 audit.

---

## Phase 0 Verified Findings (Summary)

| ID | Finding | Severity | File |
|----|---------|----------|------|
| BUG-1 | Missing `logger` import in `alert_lifecycle.py` | **Critical** — crashes on alert triage | `api/v1/alert_lifecycle.py:211` |
| BUG-2 | Undefined variable `db_url` in `db_init.py` | **High** — crashes during DB integrity checks | `db_init.py:353` |
| BUG-3 | Duplicate `DetectionFramework` class defined in two modules | **High** — unpredictable behavior at runtime | `detection_rules/framework.py:105` AND `rule_model.py:415` |
| BUG-4 | Dead/redundant `timedelta` import at bottom of `framework.py` | Low — syntax error risk, copy-paste artifact | `detection_rules/framework.py:218-219` |
| BUG-5 | Frontend sends `ids` instead of `alert_ids` for bulk triage | **High** — all bulk triage calls return 422 | `frontend/src/lib/api.ts:162` |
| BUG-6 | Four `print()` debug statements left in production rule evaluation code | Medium — console noise, no structured logging | `detection_rules/rule_model.py:326,337,369,375` |
| C3 | Duplicate `get_current_user`/`get_current_admin` definitions in `auth.py` and `deps.py` with divergent logic (auth.py has password-change-invalidation; deps.py does not) | **High** — authorization bypass risk | `api/v1/auth.py:113-168` vs `api/deps.py:24-67` |
| TODO-1 | Process tree endpoint returns empty array (stub) | Low | `api/v1/telemetry.py:232-245` |
| TODO-2 | Config signature is hardcoded `"placeholder"` | Low (documented limitation) | `api/v1/agents.py:247,296` |

---

## Changes Made in Phase 1

### Fix 1: Add missing logger to `alert_lifecycle.py`

**File:** `backend/src/sentinelwatch_backend/api/v1/alert_lifecycle.py`

```diff
  from ..deps import get_current_user, get_current_analyst
+ from ...logging import get_logger

+ logger = get_logger(__name__)
+
  router = APIRouter(prefix="/alerts", tags=["alerts"])
```

**Evidence:** Lines 19–22 now contain the import and initialization. All four `logger.info(...)` / `logger.warning(...)` calls at lines 122, 140, 211, 255 are now functional.

---

### Fix 2: Replace undefined `db_url` with `config.database.url` in `db_init.py`

**File:** `backend/src/sentinelwatch_backend/db_init.py`

```diff
- logger.warning("integrity_check_sqlite_only", database_type=db_url.split("+")[0])
+ logger.warning("integrity_check_sqlite_only", database_type=config.database.url.split("+")[0])
```

**Evidence:** Line 353 now references the `config` parameter that is passed into the function scope.

---

### Fix 3: Remove duplicate `DetectionFramework` from `framework.py`

**File:** `backend/src/sentinelwatch_backend/detection_rules/framework.py`

Removed the entire `DetectionFramework` class body (lines 105–219) which was an incomplete, stale duplicate of the one already in `rule_model.py`. The re-export in `__init__.py` continues to reference `DetectionFramework` from `rule_model.py`, which is the only remaining definition.

**Evidence:** The file now ends after the first `DetectionFramework` import block (the one in `rule_model.py`), and the dead `from datetime import timedelta` line at the bottom has been removed.

---

### Fix 4: Removed dead `timedelta` import in `framework.py`

**File:** `backend/src/sentinelwatch_backend/detection_rules/framework.py`

Removed lines 218–219:
```python
# Add timedelta import
from datetime import timedelta
```
(`timedelta` was already imported at line 13.)

---

### Fix 5: Fixed frontend bulk triage field name mismatch

**File:** `frontend/src/lib/api.ts`

```diff
- api.post('/api/v1/alerts/bulk/triage', { ids, ...data }),
+ api.post('/api/v1/alerts/bulk/triage', { alert_ids: ids, ...data }),
```

**Evidence:** Backend model at `alert_lifecycle.py:81` defines `alert_ids: List[str]`. The frontend now matches this contract.

---

### Fix 6: Converted debug prints to structured logging in `rule_model.py`

**File:** `backend/src/sentinelwatch_backend/detection_rules/rule_model.py`

Added module-level logger:
```python
import structlog
logger = structlog.get_logger(__name__)
```

Replaced four `print()` calls:
- `print(f"[DEBUG] DetectionEngine.evaluate:...")` → `logger.debug("evaluate", keys=..., source=..., parent_name=..., name=...)`
- `print(f"[DEBUG] Rule {...}: triggered={triggered}")` → `logger.debug("rule_evaluated", rule_id=..., rule_name=..., triggered=...)`
- `print(f"[DEBUG] _evaluate_condition: ...")` → `logger.debug("_evaluate_condition", rule=..., telemetry_keys=..., ...)`
- `print(f"[DEBUG] _evaluate_condition result for ...")` → `logger.debug("condition_evaluated", rule_id=..., result=...)`
- `print(f"Rule evaluation error: {e}")` + `traceback.print_exc()` → `logger.error("rule_evaluation_error", rule_id=..., error=str(e), exc_info=True)`

**Evidence:** `grep -n "print(" rule_model.py` returns no matches. Structured log calls are present at the corresponding locations.

---

### Fix 7: Consolidated auth dependencies — single source of truth

**Problem:** Two independent implementations of `get_current_user`:
- `api/v1/auth.py:113-156` — includes **password-change-invalidation logic** (checks `user.password_changed_at` against token `iat`)
- `api/deps.py:24-67` — **missing** this check entirely

This meant routes importing from `deps.py` (which is all external route modules) were skipping the critical password-change invalidation, allowing access tokens issued before a password change to remain valid indefinitely.

**Fix applied to `api/deps.py`:**
- Updated `get_current_user` in `deps.py` to include the full password-change-invalidation block (matching auth.py's implementation).
- Both files now have identical behavior.

**Fix applied to `api/v1/auth.py`:**
- Removed the local `get_current_user` and `get_current_admin` definitions (lines 113–168).
- Added re-export: `from ...api.deps import get_current_user, get_current_analyst, get_current_admin`.
- Internal route handlers (`login`, `register`, MFA endpoints) continue to work because they depend on these names via the re-export chain.

**Evidence:**
```
$ grep -rn "def get_current_user\|def get_current_admin" backend/src/
api/deps.py:24:async def get_current_user(...)
api/deps.py:95:async def get_current_admin(...)
```
Only one definition per symbol now exists. `auth.py` line 112 re-exports them.

---

## Files Modified

| # | File | Change Type |
|---|------|-------------|
| 1 | `backend/src/sentinelwatch_backend/api/v1/alert_lifecycle.py` | Added missing `logger` import & init |
| 2 | `backend/src/sentinelwatch_backend/db_init.py` | Fixed undefined `db_url` → `config.database.url` |
| 3 | `backend/src/sentinelwatch_backend/detection_rules/framework.py` | Removed duplicate `DetectionFramework` class + dead import |
| 4 | `backend/src/sentinelwatch_backend/detection_rules/rule_model.py` | Replaced `print()` with `structlog`; added `logger` import |
| 5 | `backend/src/sentinelwatch_backend/api/deps.py` | Added password-change-invalidation to `get_current_user` |
| 6 | `backend/src/sentinelwatch_backend/api/v1/auth.py` | Removed duplicate dep definitions; added re-exports from deps |
| 7 | `frontend/src/lib/api.ts` | Fixed `ids` → `alert_ids` in bulk triage call |

---

## Test Baseline

**Cannot execute tests in current sandbox.** Constraints:
- Python 3.10 available; project requires ≥3.12
- No pip install capability (proxy blocks all external connections)
- Agent venv contains Windows PE binaries incompatible with Linux sandbox
- Database exists and must not be touched

**Baseline to establish on user's VM (Windows):**
```bash
cd .\backend
python -m pytest tests/ -v --tb=short
python -m mypy src/
python -m ruff check src/
```

**Expected results after fixes:**
- The 14 existing config tests should pass (no regressions — config code unchanged).
- Any new test covering alert triage or DB integrity would previously fail due to BUG-1 / BUG-2 and should now pass.

---

## Remaining Issues (Out of Scope for Phase 1)

| Issue | Location | Priority |
|-------|----------|----------|
| TODO-1: Empty process tree response | `api/v1/telemetry.py:232-245` | Medium — needs real tree-building logic |
| TODO-2: Hardcoded config signature | `api/v1/agents.py:247,296` | Medium — needs Ed25519 signing |
| Zero test coverage outside `test_config.py` | `backend/tests/` | High — need unit tests for auth, alerts, detection engine |
| Root `tests/` directory is empty | `tests/` | High |
| No git repository initialized | Project root | High — needed before further development |
| Stale backup DB files in `backend/data/` | `sentinelwatch_testbackup.db` (155 MB) | Medium — data hygiene |
| `pyproject.toml` requires Python ≥3.12 but sandbox has 3.10 | `backend/pyproject.toml` | N/A — environment issue, resolved on user's VM |

---

## Security Impact of Phase 1 Fixes

| Fix | Security Impact |
|-----|----------------|
| BUG-1 (missing logger) | Reliability — ensures alert triage works; no direct security impact |
| BUG-2 (undefined db_url) | Reliability — prevents crash on non-SQLite DB paths |
| BUG-3 (duplicate class) | Reliability — eliminates unpredictable import behavior |
| BUG-5 (bulk triage field) | **Functional correctness** — bulk triage now actually works instead of returning 422 |
| **BUG-6 (debug prints)** | **Low-security** — information leakage of telemetry keys in logs; mitigated by using `structlog` with proper log levels |
| **C3 (consolidated auth deps)** | **Security-critical** — password-change-invalidation now runs for ALL route modules, not just auth.py handlers. Tokens issued before a password change will correctly be rejected. |

---

## Verification Evidence

All changes were verified by reading the modified files back post-edit. No runtime execution was possible in the sandbox. The user should run on their Windows VM:

```bash
cd SentinelWatch/backend
python -m pytest tests/ -v
python -m mypy src/
python -m ruff check src/
```

And confirm:
- `pytest` passes (existing 14 tests + any new tests)
- `mypy` shows no new errors introduced by our changes
- `ruff` shows no new violations
- The bulk triage endpoint in Swagger (`POST /api/v1/alerts/bulk/triage`) accepts `{alert_ids: [...], status: "..."}` instead of `{ids: [...]}`
- Alert triage (`POST /api/v1/alerts/{id}/triage`) no longer raises `NameError: name 'logger' is not defined`

---

## Phase 1 Complete

**STOP.** Awaiting approval to proceed to Phase 2.
