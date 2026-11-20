# SentinelWatch Security Design

> **Current implementation:** Agent requests use a unique 15-minute bearer access token and a rotating, hashed 90-day refresh token over HTTPS. The current enrollment API does not issue or require client certificates; agent mTLS and certificate pinning described in older design material are not implemented.

## Secure Development Lifecycle

### Code Security
- All dependencies pinned with hashes (`pip install --require-hashes`)
- `bandit` static analysis in CI
- `pip-audit` / `safety` for vulnerability scanning
- Pre-commit hooks: `ruff`, `mypy`, `bandit`
- No `eval`, `exec`, `subprocess.shell=True`, `pickle`
- Type hints mandatory (`mypy --strict`)

### Dependency Management
```toml
# pyproject.toml example
[tool.pip-audit]
# Fail on any vulnerability
fail-on-vuln = true

[tool.bandit]
exclude_dirs = ["tests"]
skips = ["B101"]  # assert_used - allowed in tests
```

### Secrets Management
- **Development**: `.env` file (gitignored), loaded via `python-dotenv`
- **Production**: Environment variables injected by orchestration
- **Agent certificates**: Windows Certificate Store (MY store) or file with ACLs
- **Database passwords**: Never in code, only via env vars
- **JWT secrets**: 256-bit random, rotated quarterly

## Agent Security Hardening

### Process Isolation
```python
# Run agent as dedicated service account
# Windows: "NT SERVICE\SentinelWatchAgent"
# - No interactive logon
# - No admin rights
# - Logon as service only
# - Deny: "Access this computer from network"
```

### Read-Only Monitoring Guarantees
| API Category | Used | Risk | Mitigation |
|--------------|------|------|------------|
| `psutil.process_iter` | ✅ | Low | Read-only |
| `psutil.Process.cmdline` | ✅ | Medium | Redact secrets |
| `psutil.Process.exe` | ✅ | Low | Read-only |
| `psutil.Process.connections` | ✅ | Low | Read-only |
| `win32service.EnumServicesStatusEx` | ✅ | Low | Read-only |
| `winreg.OpenKey` (Run keys) | ✅ | Low | Read-only |
| `win32evtlog.ReadEventLog` | ✅ | Low | Read-only |
| `win32process.OpenProcess` | ❌ | High | **Never used** |
| `win32api.CreateProcess` | ❌ | Critical | **Never used** |
| `ctypes` kernel calls | ❌ | Critical | **Never used** |

### Agent Authentication (implemented)
```
Agent Registration Flow:
1. An organization administrator creates a short-lived enrollment token.
2. The agent sends the token and endpoint identity to the registration API.
3. The backend validates and consumes the token, then returns an agent ID, access token and refresh token.
4. On Windows, the agent protects the credentials at rest with DPAPI for its service account.
5. The agent sends its access token over HTTPS and rotates it using the refresh token.
```

The registration request may include a CSR for compatibility, but the current backend does not sign or require a client certificate. Do not treat the CSR as mTLS enrollment.

### Configuration Integrity
- Config fetched from backend signed with Ed25519
- Agent verifies signature before applying
- Config version monotonic - reject downgrades
- Local fallback config (read-only) for offline operation

## Backend Security Hardening

### API Security Headers
```python
# FastAPI middleware
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response
```

### Input Validation Strategy
```python
# All API models use Pydantic v2 with strict config
class ProcessTelemetry(BaseModel):
    model_config = ConfigDict(
        extra='forbid',           # Reject unknown fields
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    pid: Annotated[int, Field(ge=0, le=4194304)]
    ppid: Annotated[int, Field(ge=0, le=4194304)]
    name: Annotated[str, Field(min_length=1, max_length=255)]
    cmdline: Annotated[str, Field(max_length=32768)]
    exe: Annotated[str, Field(max_length=4096)]
    # ... more fields with strict bounds
```

### Rate Limiting

FastAPI enforces per-IP token-bucket limits using the configured general, agent, authentication, and registration rates. A 429 response includes `Retry-After`. The buckets are process-local and bounded in memory; multi-worker or replicated deployments must enforce shared limits at a trusted gateway. The application keys requests by the direct connection peer and does not trust arbitrary `X-Forwarded-For` headers. Login throttling is IP-based only; it is not a per-account lockout.

Configured values are requests per minute with a separate burst capacity: general API `1000/2000`, agent API `100/500`, authentication `10/20`, and registration `5/10`. These are per-IP limits, not per-user or per-agent account quotas.

### Database Security
```python
# SQLAlchemy - parameterized queries only (ORM prevents injection)
# But additional defenses:
# - Database user: SELECT, INSERT, UPDATE on app tables only
# - No DDL, no TRUNCATE, no raw SQL execution
# - Row-level security for multi-tenant (future)
# - Audit table: INSERT only, no UPDATE/DELETE via GRANT
```

### Audit Logging
```python
# Immutable audit entries
class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(UUID, primary_key=True, default=uuid4)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    actor_type = Column(Enum("user", "agent", "system"), nullable=False)
    actor_id = Column(String(255), nullable=False)
    action = Column(String(100), nullable=False)  # e.g., "alert.dismiss", "rule.create"
    resource_type = Column(String(50))
    resource_id = Column(String(255))
    details = Column(JSONB)  # Structured, no PII
    ip_address = Column(String(45))  # IPv4/IPv6
    user_agent = Column(String(512))
    result = Column(Enum("success", "failure", "denied"))
    # Index on (timestamp, actor_id) for queries
```

## Frontend Security

### Content Security Policy
```html
<!-- Vite generates nonce for inline scripts -->
<meta http-equiv="Content-Security-Policy"
      content="default-src 'self';
               script-src 'self' 'nonce-{NONCE}';
               style-src 'self' 'unsafe-inline';
               img-src 'self' data:;
               connect-src 'self' wss://api.sentinelwatch.local;
               font-src 'self';">
```

### Safe Rendering Practices
```typescript
// NEVER use dangerouslySetInnerHTML
// All user data rendered via React's auto-escaping
// For rich text: DOMPurify.sanitize(html, { ALLOWED_TAGS: [] })

// API response sanitization (backend also sanitizes)
function sanitizeForDisplay(input: string): string {
  return input
    .replace(/[<>]/g, '')  // Basic XSS prevention
    .slice(0, 10000);      // Length limit
}
```

### Authentication Flow
```
1. User submits credentials → POST /auth/login
2. Backend verifies Argon2id hash
3. Returns: access_token (15min), refresh_token (7d) in HttpOnly cookies
4. Frontend stores access_token in memory (not localStorage)
5. Requests include Authorization: Bearer <access_token>
6. On 401: POST /auth/refresh with cookie → new access_token
7. Refresh token rotation: old token invalidated, new issued
8. Reuse detection: if same refresh token used twice → revoke all user sessions
```

## Network Security

### TLS Configuration
```yaml
# Minimum TLS 1.2, prefer 1.3
ssl_ciphers: "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305"
ssl_protocols: "TLSv1.2 TLSv1.3"
ssl_prefer_server_ciphers: on
# HSTS
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
```

### Certificate Management
- **Agent ↔ Backend**: Private PKI (smallstep or HashiCorp Vault)
  - Root CA: offline, air-gapped
  - Intermediate CA: online, signs agent certs (90-day TTL)
  - Agent certs: 90-day TTL, auto-renewal at 60 days
- **Backend ↔ Frontend**: Public CA (Let's Encrypt) or internal PKI
- **Certificate Pinning**: Agent pins backend CA fingerprint

## Data Protection

### Data Classification
The retention values below are target policy defaults from configuration. No scheduled purge job currently enforces them; administrators must manage database retention and backups until that job exists.

| Data Type | Classification | Target Retention | Encryption |
|-----------|---------------|-----------|------------|
| Process telemetry | Operational | 30 days | At-rest (AES-256) |
| Command lines | Sensitive* | 30 days | At-rest + redacted |
| Alerts | Security | 1 year | At-rest |
| Audit logs | Compliance | 7 years | At-rest + WORM |
| Agent certificates | Secret | 90 days | At-rest + transit |
| User credentials | Secret | Indefinite | Argon2id hash only |

*Command lines redacted before storage

### Data Minimization
- Collect only fields needed for detection rules
- No full memory dumps, no file contents, no keystrokes
- Network connections: only metadata (PID, remote IP/port, state)
- No screen captures, no clipboard, no audio/video

## Incident Response

### Compromise Scenarios
| Scenario | Detection | Response |
|----------|-----------|----------|
| Agent cert stolen | Anomalous geo/IP, concurrent heartbeats | Revoke cert, re-enroll agent |
| Backend DB breach | Audit log anomalies, unexpected queries | Rotate all secrets, restore from backup |
| Analyst account compromised | Impossible travel, new device | Force MFA reset, revoke sessions |
| Detection rule tampered | Config signature verification fails | Alert, rollback to last signed config |

### Forensic Readiness
- All telemetry hashed (SHA-256) on receipt
- Alert evidence includes raw telemetry snapshot
- Chain of custody: audit log + signed exports
- Export format: JSON Lines with metadata headers

## Compliance Considerations
- **GDPR**: No personal data collected (process metadata only)
- **SOC 2**: Audit logging, access control, encryption
- **NIST 800-53**: Audit (AU), Access Control (AC), System Integrity (SI)
- **MITRE ATT&CK**: Rule mapping for coverage tracking
