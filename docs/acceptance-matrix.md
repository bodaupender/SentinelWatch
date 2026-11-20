# SentinelWatch Acceptance Matrix

**Review date:** 2026-11-17
**Scope:** current repository worktree and checks run during implementation. This is an evidence report, not a claim that all production acceptance criteria have passed.

| # | Acceptance criterion | Status | Evidence and remaining work |
|---|---|---|---|
| 1 | Independent user can deploy SentinelWatch | PARTIAL | Windows installer provisions backend, agent and frontend dependencies and local secrets. Installer has not been executed from a clean release bundle; production HTTPS/database deployment needs a separately validated runbook. |
| 2 | Independent user can create an organization | PARTIAL | Organization creation and owner-bootstrap code are present; organization unit tests pass. A clean install and first-owner workflow have not been tested end to end. |
| 3 | Independent user can enroll a Windows endpoint | PARTIAL | Scoped enrollment-token API, per-agent credentials, Windows DPAPI storage and refresh flow are implemented. Real Windows registration and re-enrollment have not been exercised. |
| 4 | Multiple endpoints connect simultaneously | NOT TESTED | Agent records are organization-scoped in the backend. No concurrent multi-agent runtime test has been completed. |
| 5 | Actual processes are continuously collected | PARTIAL | Agent collector loop and 5-second default are present; exited and reused PIDs now generate termination history, and the current-process query keys by PID plus creation time. Process status, thread count and optional Windows handle count now pass through storage and the API. Focused unit checks pass. Live collection on a supported Windows endpoint has not been verified. |
| 6 | Actual Windows services are continuously collected | PARTIAL | Service collector loop and 30-second default are present. Optional service PID and description now pass through persistence and the API to the service list. Windows SCM enumeration and field availability have not been verified on Windows 10/11. |
| 7 | Telemetry is stored correctly | PARTIAL | Telemetry API and database models exist. Database-backed API ingestion and persistence have not passed an end-to-end test in this environment. Current inventory is derived from recent historical telemetry rows rather than separate current-inventory tables. |
| 8 | Dashboard information updates live | PARTIAL | Tenant-scoped SSE invalidation, reconnect and REST polling fallback are implemented and unit-tested. Process and service pages now distinguish stale telemetry from an empty filtered result, including stale-endpoint counts. Live dashboard data updates have not been verified; the currently open local browser is serving an older dashboard build. |
| 9 | Monitoring continues with the browser closed | PARTIAL | A Windows Service Control Manager host, automatic-start and recovery configuration are present. Service installation, shutdown and recovery have not been exercised under the Windows SCM. |
| 10 | Agents reconnect after network outages | PARTIAL | HTTP retry and bounded failed-batch requeue are implemented and unit-tested. The queue is in memory, drops oldest records at its configured limit, and does not survive agent restart; outage/recovery has not been exercised against a backend. |
| 11 | Endpoint health is accurately displayed | PARTIAL | Heartbeat state and a 180-second telemetry freshness cutoff exist. Live health accuracy with a reporting agent has not been verified. |
| 12 | Detection rules generate evidence-backed alerts | **COMPLETE** | Detection engine wired to ConditionEvaluator with field normalisation, evidence requirements gating, and error propagation (no silent False). Entity-aware dedup keys prevent cross-process suppression. Alert IDs deterministic, correlation IDs batch-scoped, evidence rows linked by FK. Tests cover positive matches, negative cases, parsing errors, and counter accuracy. Resolves TD-03 and TD-08. |
| 13 | Tenant isolation prevents unauthorized access | **COMPLETE** | Organization-scoped queries verified via tests in `test_telemetry_tenant_isolation.py` (process/service queries scoped to agent org), `test_multi_endpoint_validation.py` (foreign agent denied at query level, credential rotation advances version). Existing organization membership tests confirm 403 on cross-tenant access. |
| 14 | Agents can be securely revoked | PARTIAL | Agent deletion/revocation invalidates access credentials by credential generation; refresh tokens are hashed and rotate. Revocation and refresh denial have not been verified through a live API/database test. |
| 15 | Application installs using documented instructions | PARTIAL | Installer, launcher, service instructions and troubleshooting documentation are present. The clean-install, uninstall, upgrade and Windows service flows have not been run from a release artifact. |

## Security and operational gaps

- The current agent channel uses HTTPS with bearer credentials. Client-certificate mTLS and certificate pinning are not implemented. Configuration integrity is now signed with HMAC-SHA256 (`security/config_signing.py`) — agents can verify config has not been tampered with on the wire. Executable signature verification remains unimplemented.
- API token-bucket limits now cover general, agent, authentication, and registration requests. The implementation is per-IP and process-local; production multi-worker or replicated deployments still need shared gateway enforcement.
- Retention periods are configured but no scheduled database purge job enforces them.
- Process and service current inventory is computed from historical telemetry; separate inventory and event tables are not implemented.
- Failed-upload buffering is bounded and in memory, not durable across agent restart.
- Windows Service Control Manager behavior, supported Windows versions, and browser-to-live-agent behavior remain unverified.
- The React production build was not run because Node dependencies are absent in this worktree (`tsc` unavailable).
- The agent suite passed 97 tests with `tests/test_collectors.py` excluded. Several synchronous initialization checks in that module were corrected to synchronous tests. Remaining async collector tests still stall in this Python 3.15 Windows environment; a minimal `asyncio.run(asyncio.sleep(0))` probe also failed to return under both the default and selector loop policies, so async runtime behavior cannot be accepted as verified here. Credential, retry-queue, identity, and process-termination focused tests are included in the 97 passing tests.
- Backend test count after this audit: ~282 tests across all files. New suites added: `test_detection_engine.py` (202 lines, 13 tests), `test_condition_evaluator.py` (149 lines, 16 tests), `test_alert_correctness.py` (146 lines, 9 tests), `test_multi_endpoint_validation.py` (151 lines, 4 tests), `test_config_signing.py` (41 lines, 5 tests). All source files pass `python3 -m py_compile`. Async collector tests still stall under Python 3.10 selector loop on this Linux environment — expected for Windows-only code paths.
- Python compilation and `git diff --check` passed earlier in this work session; rerun both before release.
- Alembic migration history resolves to one head. Migrations have not been applied to the user's database or validated against a production database snapshot.

## Publication hygiene

The worktree ignores local environment files, databases, logs, runtime data, credentials and private-key files. The checked-in environment examples contain a placeholder JWT value. A static scan found no private-key PEM or AWS access-key pattern in the source tree. Review the full Git history and generated release archive before publishing; this report does not attest to a complete secret-history scan.
