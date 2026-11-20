# SentinelWatch Threat Model

> **Implementation status:** This is a threat model, not proof that every listed control is deployed. The current agent channel uses HTTPS with per-agent bearer access/refresh credentials; client-certificate mTLS, certificate pinning, append-only database enforcement, and bundled container hardening are not implemented. See the Windows Agent Guide and Security Design for current behavior.

## System Boundaries

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SENTINELWATCH SYSTEM                             │
│  ┌─────────────┐      ┌──────────────┐      ┌─────────────────────┐    │
│  │   AGENT     │      │   BACKEND    │      │   FRONTEND (SOC)    │    │
│  │  (Endpoint) │◄────►│   (API/DB)   │◄────►│    (Analyst UI)     │    │
│  └──────┬──────┘      └──────┬───────┘      └──────────┬──────────┘    │
│         │                    │                          │               │
└─────────┼────────────────────┼──────────────────────────┼───────────────┘
          │                    │                          │
    ┌─────▼─────┐        ┌─────▼─────┐            ┌──────▼──────┐
    │  Windows  │        │  Network  │            │  Analyst    │
    │  Endpoint │        │  (TLS)    │            │  Workstation│
    └───────────┘        └───────────┘            └─────────────┘
```

## Trust Boundaries

| Boundary | Description | Trust Level |
|----------|-------------|-------------|
| Agent ↔ Backend | HTTPS with per-agent bearer credentials (mTLS not implemented) | Authenticated; requires trusted TLS |
| Backend ↔ Frontend | HTTPS + JWT auth | High (authenticated analysts) |
| Agent ↔ Windows OS | Local system APIs | High (agent runs locally) |
| Backend ↔ Database | Local/private network | High |
| External → Backend | Internet-facing API | **Untrusted** |

## Threat Scenarios

### 1. Untrusted Endpoint Telemetry
**Threat**: Compromised or malicious endpoint sends fabricated telemetry
- **Impact**: False alerts, alert fatigue, missed detections, resource exhaustion
- **Mitigations**:
  - Unique, short-lived access credentials per agent; refresh tokens are rotated and stored as hashes
  - Telemetry schema validation (Pydantic models) - reject malformed data
  - Rate limiting per agent (max events/sec)
  - Anomaly detection on telemetry patterns (e.g., impossible process trees)
  - Agent heartbeat monitoring - detect cloned/replayed agents

### 2. Malicious or Malformed Event Data
**Threat**: Crafted telemetry exploits parser vulnerabilities
- **Impact**: RCE, DoS, data corruption
- **Mitigations**:
  - Strict Pydantic validation with `extra='forbid'`
  - Size limits on all fields (command line max 32KB, etc.)
  - No `eval()`, `exec()`, `pickle.loads()` on telemetry
  - Sanitize command lines before storage/logging (redact secrets)

### 3. API Abuse
**Threat**: Unauthenticated or authenticated attackers abuse API endpoints
- **Impact**: Data exfiltration, DoS, alert manipulation
- **Mitigations**:
  - JWT authentication required for all endpoints except `/health`, `/agents/register`
  - Role-based access control (RBAC): `analyst`, `admin`, `agent`
  - Rate limiting: 100 req/min per IP, 1000 req/min per user
  - API versioning, deprecated endpoint removal
  - Request/response size limits

### 4. Authentication Attacks
**Threat**: Credential stuffing, token theft, session hijacking
- **Impact**: Unauthorized dashboard access, alert suppression
- **Mitigations**:
  - Argon2id password hashing (via `passlib`)
  - Short-lived JWT access tokens (15 min), refresh tokens (7 days)
  - Refresh token rotation + reuse detection
  - Secure, HttpOnly, SameSite=Strict cookies
  - MFA support (TOTP) for admin accounts
  - Account lockout after 5 failed attempts (15 min)
  - Audit log all auth events

### 5. Privilege Escalation Risks
**Threat**: Agent or backend component exploited for higher privileges
- **Impact**: SYSTEM/root access on endpoint or server
- **Mitigations**:
  - Agent runs as standard user (non-admin)
  - Agent only uses read-only Windows APIs (WMI, PDH, Event Log)
  - No `SeDebugPrivilege`, no process injection, no kernel drivers
  - Backend runs in container with dropped capabilities
  - Database user: read/write own tables only, no DDL

### 6. Sensitive Information in Command Lines
**Threat**: Process command lines contain passwords, tokens, keys
- **Impact**: Credential leakage in telemetry/logs/database
- **Mitigations**:
  - Redact common secret patterns before storage:
    - `--password=`, `--token=`, `--key=`, `--secret=`
    - `AWS_ACCESS_KEY_ID`, `GITHUB_TOKEN`, `DATABASE_URL`
    - Base64 strings > 20 chars (potential tokens)
  - Configurable redaction rules
  - Never log full command lines at INFO level

### 7. Agent Impersonation
**Threat**: Attacker registers fake agent to inject false data
- **Impact**: Polluted dataset, missed real threats
- **Mitigations**:
  - Agent registration requires a scoped, short-lived enrollment token
  - Backend binds credentials to an agent database record and revokes by credential generation
  - CSR is accepted for compatibility but is not signed or used for client-certificate authentication
  - Heartbeats update last-seen state; signed timestamp replay protection is not implemented

### 8. Database Tampering
**Threat**: Direct DB access modifies alerts, deletes evidence
- **Impact**: Covered tracks, lost forensic data
- **Mitigations**:
  - Database user: no `DROP`, `TRUNCATE`, `ALTER` permissions
  - Soft deletes only (`deleted_at` timestamp)
  - Immutable audit table (append-only, no UPDATE/DELETE)
  - Daily automated backups with integrity checks
  - WAL-G or similar for point-in-time recovery

### 9. Dashboard Injection Attacks
**Threat**: XSS via alert data, process names, command lines rendered in UI
- **Impact**: Analyst session hijack, credential theft
- **Mitigations**:
  - React auto-escapes by default - use `dangerouslySetInnerHTML` never
  - Content Security Policy: `script-src 'self'`
  - Sanitize all user-controlled strings on backend before sending
  - Truncate long strings in API responses

### 10. False-Positive Risks
**Threat**: Detection rules generate excessive false alerts
- **Impact**: Alert fatigue, missed real threats, wasted analyst time
- **Mitigations**:
  - Rule testing framework with historical data
  - Staging environment for new rules
  - Severity scoring with auto-triage (low severity → no notification)
  - Feedback loop: analysts mark FP, rules auto-tune
  - Rule versioning with rollback

### 11. Excessive Resource Consumption
**Threat**: Agent or backend consumes excessive CPU/memory/disk/network
- **Impact**: Endpoint slowdown, backend DoS, data loss
- **Mitigations**:
  - Agent: configurable collection intervals, CPU/memory limits via job object
  - Agent: batch telemetry, compress (zstd), exponential backoff on errors
  - Backend: request timeouts, connection pooling, circuit breakers
  - Database: connection limits, query timeouts, index optimization
  - Monitoring: Prometheus metrics on all components

## Attack Surface Summary

| Component | External Attack Surface | Internal Attack Surface |
|-----------|------------------------|------------------------|
| Agent | None (outbound only) | Windows APIs, local config file |
| Backend | `/health`; agent registration requires an enrollment token | Other API endpoints require authenticated user or agent credentials |
| Frontend | Static assets only | API calls (authenticated) |
| Database | None (private network) | Backend ORM only |
| Config | File system (agent) | Backend config API (admin only) |

## Security Requirements Traceability

| Requirement | Implementation |
|-------------|----------------|
| REQ-001: Agent authenticity | Unique bearer credentials after scoped enrollment; mTLS remains a gap |
| REQ-002: Data integrity in transit | TLS 1.3, certificate pinning |
| REQ-003: Least privilege agent | Non-admin user, read-only APIs |
| REQ-004: Secret protection | Redaction pipeline, env var config |
| REQ-005: Audit trail | Append-only audit log, signed entries |
| REQ-006: Access control | RBAC + JWT + MFA |
| REQ-007: Input validation | Pydantic models, size limits |
| REQ-008: Resource limits | Rate limits, timeouts, quotas |
| REQ-009: Secure defaults | Deny-by-default, explicit allowlists |
| REQ-010: Incident response | Alert correlation, evidence preservation |
