# SentinelWatch Configuration Guide

**Version:** 1.0
**Date:** 2026-11-12

---

## Configuration Overview

SentinelWatch uses a layered configuration system with the following precedence (highest to lowest):

1. **Environment Variables** (highest priority) - `SW_BACKEND_*` prefix
2. **YAML Configuration File** - `config/backend.yaml`
3. **Default Values** (lowest priority) - Built-in defaults

Environment variables use the prefix `SW_BACKEND_` with double underscores for nesting:
- `SW_BACKEND_SERVER__PORT=8000` → `server.port`
- `SW_BACKEND_AUTH__JWT_SECRET=secret` → `auth.jwt_secret`

---

## Environment-Specific Configurations

### Development
```yaml
server:
  host: "0.0.0.0"
  port: 8000
  debug: true
  workers: 1

database:
  url: "sqlite+aiosqlite:///./data/sentinelwatch.db"

tls:
  enabled: false

cors:
  allow_all: true
  allowed_origins: "http://localhost:5173"

logging:
  level: "DEBUG"
  format: "console"
```

### Testing
```yaml
server:
  debug: true

database:
  url: "sqlite+aiosqlite:///./test.db"

tls:
  enabled: false

logging:
  level: "WARNING"
  file: ""
```

### Demonstration
```yaml
server:
  debug: false

database:
  url: "postgresql+asyncpg://sentinelwatch:pass@localhost:5432/sentinelwatch_demo"

tls:
  enabled: true
  cert_file: "/etc/sentinelwatch/certs/server.crt"
  key_file: "/etc/sentinelwatch/certs/server.key"

cors:
  allow_all: false
  allowed_origins: "https://demo.sentinelwatch.local"

logging:
  level: "INFO"
  format: "json"
  file: "/var/log/sentinelwatch/backend.log"
```

### Production
```yaml
server:
  host: "0.0.0.0"
  port: 8000
  debug: false
  workers: 4
  timeout: 30

database:
  url: "postgresql+asyncpg://sentinelwatch:${DB_PASSWORD}@db:5432/sentinelwatch"
  pool_size: 20
  max_overflow: 40

tls:
  enabled: true
  cert_file: "/etc/sentinelwatch/certs/server.crt"
  key_file: "/etc/sentinelwatch/certs/server.key"
  ca_file: "/etc/sentinelwatch/certs/ca.crt"
  require_client_cert: true

cors:
  allow_all: false
  allowed_origins: "https://dashboard.sentinelwatch.local"
  allow_credentials: true

rate_limiting:
  enabled: true
  default_limit: 1000
  agent_limit: 100
  auth_limit: 10

logging:
  level: "INFO"
  format: "json"
  file: "/var/log/sentinelwatch/backend.log"
  max_size_mb: 100
  backup_count: 10
  structured: true

audit:
  enabled: true
  file: "/var/log/sentinelwatch/audit.log"
  max_size_mb: 500
  backup_count: 10
```

---

## Required Environment Variables

### Critical (Must Set in Production)

| Variable | Description | Example |
|----------|-------------|---------|
| `SW_BACKEND_AUTH__JWT_SECRET` | **CRITICAL** - 32+ char random string | `openssl rand -hex 32` |
| `SW_BACKEND_DATABASE__URL` | Database connection string | `postgresql+asyncpg://user:pass@host:5432/db` |
| `SW_BACKEND_SERVER__DEBUG` | `false` for production | `false` |

### Recommended for Production

| Variable | Description | Default |
|----------|-------------|---------|
| `SW_BACKEND_SERVER__HOST` | Bind address | `0.0.0.0` |
| `SW_BACKEND_SERVER__PORT` | Port number | `8000` |
| `SW_BACKEND_SERVER__WORKERS` | Gunicorn workers | `4` |
| `SW_BACKEND_TLS__ENABLED` | Enable HTTPS | `true` |
| `SW_BACKEND_TLS__CERT_FILE` | SSL certificate path | `/etc/sentinelwatch/certs/server.crt` |
| `SW_BACKEND_TLS__KEY_FILE` | SSL key path | `/etc/sentinelwatch/certs/server.key` |
| `SW_BACKEND_CORS__ALLOWED_ORIGINS` | Allowed origins | `https://dashboard.example.com` |
| `SW_BACKEND_LOGGING__FILE` | Log file path | `/var/log/sentinelwatch/backend.log` |

---

## Configuration Validation Checklist

### Pre-Deployment Validation

Run this checklist before each deployment:

- [ ] **JWT Secret**: `SW_BACKEND_AUTH__JWT_SECRET` is set to 32+ character random string (not default)
- [ ] **Database URL**: Points to correct production database
- [ ] **Debug Mode**: `SW_BACKEND_SERVER__DEBUG=false`
- [ ] **TLS Enabled**: `SW_BACKEND_TLS__ENABLED=true`
- [ ] **TLS Certificates**: Certificate and key files exist and are readable
- [ ] **CORS Origins**: `SW_BACKEND_CORS__ALLOWED_ORIGINS` matches frontend domain
- [ ] **Database Credentials**: Not hardcoded, loaded from environment
- [ ] **Rate Limiting**: Enabled with appropriate limits
- [ ] **Audit Logging**: Enabled with appropriate retention
- [ ] **Log File Paths**: Directories exist and are writable
- [ ] **Certificate Paths**: TLS cert/key files exist and are valid
- [ ] **Agent Config**: Enrollment token configured if auto-registration enabled

### Validation Commands

```bash
# Validate configuration
cd backend && python -c "
import os
os.environ['SW_BACKEND_SERVER__DEBUG'] = 'false'
os.environ['SW_BACKEND_AUTH__JWT_SECRET'] = 'your-production-secret-here'
import sys; sys.path.insert(0, 'src')
from sentinelwatch_backend.config import BackendConfig
config = BackendConfig()
print('Config valid!')
print(f'Debug: {config.server.debug}')
print(f'JWT Secret length: {len(config.auth.jwt_secret)}')
"
```

### Configuration Files

| File | Purpose | Override Method |
|------|---------|-----------------|
| `config/backend.yaml` | Base configuration | Copy to `config/backend.local.yaml` |
| `.env` | Environment overrides | Never commit |
| `.env.example` | Template | Copy to `.env` |

---

## Secure Secret Management

### Development
```bash
# .env file (gitignored)
SW_BACKEND_AUTH__JWT_SECRET=dev-secret-change-me
SW_BACKEND_DATABASE__URL=sqlite+aiosqlite:///./data/sentinelwatch.db
```

### Production Options

**Option 1: Environment Variables (Docker/K8s)**
```yaml
# docker-compose.yml
environment:
  - SW_BACKEND_AUTH__JWT_SECRET=${JWT_SECRET}
  - SW_BACKEND_DATABASE__URL=postgresql+asyncpg://user:${DB_PASSWORD}@db:5432/sentinelwatch
```

**Option 2: Kubernetes Secrets**
```yaml
# k8s secret
apiVersion: v1
kind: Secret
metadata:
  name: sentinelwatch-secrets
type: Opaque
stringData:
  JWT_SECRET: "your-32-char-random-secret"
  DB_PASSWORD: "database-password"
```

**Option 3: HashiCorp Vault**
```hcl
# vault policy
path "secret/data/sentinelwatch/*" {
  capabilities = ["read"]
}
```

---

## CORS Configuration

### Development
```yaml
cors:
  allow_all: true
  allowed_origins: "http://localhost:5173"
```

### Production
```yaml
cors:
  allow_all: false
  allowed_origins: "https://dashboard.yourdomain.com"
  allow_credentials: true
  allowed_methods: "GET,POST,PUT,PATCH,DELETE,OPTIONS"
  allowed_headers: "Authorization,Content-Type,X-Request-ID"
```

---

## Rate Limiting Configuration

```yaml
rate_limiting:
  enabled: true
  default_limit: 1000      # requests per minute
  default_burst: 2000      # burst allowance
  agent_limit: 100         # agent telemetry
  agent_burst: 500
  auth_limit: 10           # login attempts
  auth_burst: 20
  register_limit: 5        # agent registration
  register_burst: 10
```

---

## Logging Configuration

```yaml
logging:
  level: "INFO"              # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "json"             # json or console
  file: "/var/log/sentinelwatch/backend.log"
  max_size_mb: 100
  backup_count: 5
  structured: true

audit:
  enabled: true
  file: "/var/log/sentinelwatch/audit.log"
  max_size_mb: 500
  backup_count: 10
  include_bodies: false
```

### Log Rotation

Logs are automatically rotated when they reach `max_size_mb`. Keep `backup_count` files.

```bash
# Manual rotation
logrotate -f /etc/logrotate.d/sentinelwatch
```

---

## Database Migration Strategy

### Development (Auto-create)
```yaml
server:
  debug: true  # Enables auto-create
```

### Production (Alembic Migrations)
```bash
# Generate migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Check current revision
alembic current

# History
alembic history
```

### Backup Strategy
```bash
# PostgreSQL backup
pg_dump -h localhost -U sentinelwatch sentinelwatch > backup_$(date +%Y%m%d).sql

# Restore
psql -h localhost -U sentinelwatch sentinelwatch < backup_20241112.sql
```

---

## Agent Configuration

The backend serves agent configuration via `/agent/v1/config/poll`. Key settings:

```yaml
agent_config:
  collection_intervals:
    process: 5
    service: 30
    startup: 3600
    eventlog: 10
    health: 60
    heartbeat: 30
    config: 300
  batching:
    max_size: 100
    max_interval: 5.0
    compress: true
    compression_level: 3
  eventlog_channels:
    - "Security"
    - "System"
    - "Application"
```

---

## Validation Script

Create `scripts/validate_config.py`:

```python
#!/usr/bin/env python3
"""Validate SentinelWatch configuration before deployment."""

import os
import sys
from pathlib import Path

def check_env_var(name: str, required: bool = False, min_length: int = 0) -> bool:
    value = os.getenv(name)
    if value is None:
        if required:
            print(f"❌ MISSING: {name}")
            return False
        return True
    if min_length and len(value) < min_length:
        print(f"❌ TOO SHORT: {name} (min {min_length} chars)")
        return False
    print(f"✅ {name}")
    return True

def main():
    print("=== SentinelWatch Configuration Validation ===\n")

    all_ok = True

    # Critical
    all_ok &= check_env_var("SW_BACKEND_AUTH__JWT_SECRET", required=True, min_length=32)
    all_ok &= check_env_var("SW_BACKEND_DATABASE__URL", required=True)
    all_ok &= check_env_var("SW_BACKEND_SERVER__DEBUG", required=True)

    # Recommended
    all_ok &= check_env_var("SW_BACKEND_SERVER__HOST")
    all_ok &= check_env_var("SW_BACKEND_SERVER__PORT")
    all_ok &= check_env_var("SW_BACKEND_SERVER__WORKERS")
    all_ok &= check_env_var("SW_BACKEND_TLS__ENABLED")
    all_ok &= check_env_var("SW_BACKEND_TLS__CERT_FILE")
    all_ok &= check_env_var("SW_BACKEND_TLS__KEY_FILE")
    all_ok &= check_env_var("SW_BACKEND_CORS__ALLOWED_ORIGINS")
    all_ok &= check_env_var("SW_BACKEND_LOGGING__FILE")

    # Database specific
    db_url = os.getenv("SW_BACKEND_DATABASE__URL", "")
    if db_url.startswith("postgresql"):
        all_ok &= check_env_var("SW_BACKEND_DATABASE__POOL_SIZE")

    print(f"\n{'='*50}")
    if all_ok:
        print("✅ ALL CHECKS PASSED - Ready for deployment")
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Fix before deployment")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

Run with: `python scripts/validate_config.py`
