# SentinelWatch Backend Deployment Guide

**Version:** 1.0
**Date:** 2026-11-12

---

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.11+ | 3.11+ |
| PostgreSQL | 15+ | 15+ |
| Redis | 7+ | 7+ |
| RAM | 2 GB | 4 GB+ |
| CPU | 2 cores | 4+ cores |
| Disk | 10 GB | 50 GB+ |

### System Packages (Ubuntu/Debian)
```bash
sudo apt-get update && sudo apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    postgresql-15 postgresql-client-15 \
    redis-server \
    nginx \
    build-essential \
    libpq-dev \
    libssl-dev \
    pkg-config
```

---

## Installation

### 1. Create Service User
```bash
sudo useradd -r -s /bin/bash -d /opt/sentinelwatch -m sentinelwatch
sudo usermod -aG ssl-cert sentinelwatch  # For TLS certs
```

### 2. Create Directory Structure
```bash
sudo -u sentinelwatch mkdir -p /opt/sentinelwatch/{backend,frontend,config,logs,data,certs}
sudo chmod 750 /opt/sentinelwatch/logs
sudo chmod 700 /opt/sentinelwatch/certs
```

### 3. Python Virtual Environment
```bash
cd /opt/sentinelwatch/backend
sudo -u sentinelwatch python3.11 -m venv venv
sudo -u sentinelwatch ./venv/bin/pip install --upgrade pip setuptools wheel
sudo -u sentinelwatch ./venv/bin/pip install -r requirements.txt
```

### 4. Install Production Dependencies
```bash
cd /opt/sentinelwatch/backend
sudo -u sentinelwatch ./venv/bin/pip install gunicorn uvloop httptools
```

---

## Database Setup

### PostgreSQL Setup
```bash
sudo -u postgres psql << 'EOF'
CREATE USER sentinelwatch WITH PASSWORD 'secure_password_here';
CREATE DATABASE sentinelwatch OWNER sentinelwatch;
GRANT ALL PRIVILEGES ON DATABASE sentinelwatch TO sentinelwatch;
EOF

# Test connection
psql -h localhost -U sentinelwatch -d sentinelwatch -c "SELECT version();"
```

### Initialize Database
```bash
cd /opt/sentinelwatch/backend
sudo -u sentinelwatch ./venv/bin/python -c "
import os
os.environ['SW_BACKEND_SERVER__DEBUG'] = 'false'
os.environ['SW_BACKEND_AUTH__JWT_SECRET'] = 'your-production-secret'
import sys; sys.path.insert(0, 'src')
from sentinelwatch_backend.database import init_database
import asyncio
asyncio.run(init_database())
print('Database initialized successfully')
"
```

### Run Migrations
```bash
cd /opt/sentinelwatch/backend
sudo -u sentinelwatch ./venv/bin/alembic upgrade head
```

---

## Configuration

### 1. Create Production Config
```bash
cd /opt/sentinelwatch/config
sudo -u sentinelwatch cp backend.yaml.example backend.yaml
sudo -u sentinelwatch vim backend.yaml  # Edit with production values
```

### 2. Set Environment Variables
```bash
# Create systemd environment file
sudo tee /etc/sentinelwatch/env << 'EOF'
SW_BACKEND_SERVER__DEBUG=false
SW_BACKEND_AUTH__JWT_SECRET=your-32-char-random-secret-here
SW_BACKEND_DATABASE__URL=postgresql+asyncpg://sentinelwatch:password@localhost:5432/sentinelwatch
SW_BACKEND_SERVER__DEBUG=false
SW_BACKEND_TLS__ENABLED=true
SW_BACKEND_TLS__CERT_FILE=/opt/sentinelwatch/certs/server.crt
SW_BACKEND_TLS__KEY_FILE=/opt/sentinelwatch/certs/server.key
SW_BACKEND_CORS__ALLOWED_ORIGINS=https://dashboard.yourdomain.com
SW_BACKEND_LOGGING__FILE=/opt/sentinelwatch/logs/backend.log
EOF

sudo chmod 640 /opt/sentinelwatch/env
sudo chown root:sentinelwatch /opt/sentinelwatch/env
```

### 3. Generate TLS Certificates
```bash
cd /opt/sentinelwatch/certs

# For production: use Let's Encrypt or your CA
# For demo: self-signed
openssl req -x509 -newkey rsa:4096 -keyout server.key -out server.crt \
    -days 365 -nodes -subj "/CN=api.yourdomain.com"

# Set permissions
chmod 600 server.key
chmod 644 server.crt
chown sentinelwatch:sentinelwatch server.key server.crt
```

---

## Systemd Service

### Create Service File
```bash
sudo tee /etc/systemd/system/sentinelwatch-backend.service << 'EOF'
[Unit]
Description=SentinelWatch Backend API
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=notify
User=sentinelwatch
Group=sentinelwatch
WorkingDirectory=/opt/sentinelwatch/backend
EnvironmentFile=/opt/sentinelwatch/env
ExecStart=/opt/sentinelwatch/backend/venv/bin/gunicorn \
    sentinelwatch_backend.main:create_app \
    --factory \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --worker-connections 1000 \
    --max-requests 10000 \
    --max-requests-jitter 100 \
    --timeout 30 \
    --keep-alive 5 \
    --log-level info \
    --access-logfile /opt/sentinelwatch/logs/access.log \
    --error-logfile /opt/sentinelwatch/logs/error.log \
    --capture-output \
    --enable-stdio-inheritance
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=30
Restart=on-failure
RestartSec=5

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/sentinelwatch/logs /opt/sentinelwatch/data
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
EOF
```

### Enable and Start
```bash
sudo systemctl daemon-reload
sudo systemctl enable sentinelwatch-backend
sudo systemctl start sentinelwatch-backend
sudo systemctl status sentinelwatch-backend
```

---

## Nginx Reverse Proxy

### Configuration
```bash
sudo tee /etc/nginx/sites-available/sentinelwatch << 'EOF'
upstream sentinelwatch_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name api.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /opt/sentinelwatch/certs/server.crt;
    ssl_certificate_key /opt/sentinelwatch/certs/server.key;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";

    # API proxy
    location / {
        proxy_pass http://sentinelwatch_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;

        proxy_read_timeout 30s;
        proxy_send_timeout 30s;

        # Buffering for uploads
        proxy_request_buffering off;
    }

    # Health check (no auth)
    location /health {
        proxy_pass http://sentinelwatch_backend;
        access_log off;
    }

    # Metrics (optional, restrict access)
    location /metrics {
        allow 10.0.0.0/8;  # Internal monitoring
        deny all;
        proxy_pass http://sentinelwatch_backend;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/sentinelwatch /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Health Checks

### Backend Health
```bash
# Quick health check
curl -s https://api.yourdomain.com/health | jq .

# Expected response:
# {
#   "status": "healthy",
#   "timestamp": "2026-11-12T10:00:00Z",
#   "version": "0.1.0"
# }
```

### Readiness Check
```bash
curl -s https://api.yourdomain.com/ready | jq .
```

### Database Connectivity
```bash
curl -s https://api.yourdomain.com/health/detailed | jq .
```

### Application Logs
```bash
# Follow logs
sudo journalctl -u sentinelwatch-backend -f

# Or file logs
tail -f /opt/sentinelwatch/logs/backend.log
tail -f /opt/sentinelwatch/logs/access.log
```

---

## Backup & Restore

### Database Backup
```bash
#!/bin/bash
# /opt/sentinelwatch/scripts/backup.sh

BACKUP_DIR="/opt/sentinelwatch/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="sentinelwatch"
DB_USER="sentinelwatch"

mkdir -p $BACKUP_DIR

pg_dump -h localhost -U sentinelwatch -d sentinelwatch \
    --no-owner --no-privileges \
    | gzip > $BACKUP_DIR/sentinelwatch_${DATE}.sql.gz

# Keep last 30 days
find $BACKUP_DIR -name "sentinelwatch_*.sql.gz" -mtime +30 -delete

echo "Backup completed: sentinelwatch_${DATE}.sql.gz"
```

### Restore
```bash
# Restore from backup
gunzip -c /opt/sentinelwatch/backups/sentinelwatch_20261112_120000.sql.gz | \
    psql -h localhost -U sentinelwatch -d sentinelwatch
```

---

## Monitoring

### Prometheus Metrics
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'sentinelwatch-backend'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

### Key Metrics to Monitor
| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `http_requests_total` | Request rate | > 1000/min |
| `http_request_duration_seconds` | Latency | > 1s p95 |
| `db_connections_active` | DB connections | > 80% pool |
| `agent_heartbeat_total` | Agent heartbeats | < expected |
| `alert_generated_total` | Alert rate | > baseline |

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError` | Venv not activated | Use `/opt/sentinelwatch/backend/venv/bin/python` |
| `OperationalError: unable to open database` | SQLite path | Check `data/` directory exists and writable |
| `ValidationError: JWT secret` | Default secret in prod | Set `SW_BACKEND_AUTH__JWT_SECRET` env var |
| `ssl.SSLError` | Cert mismatch | Check cert/key paths and permissions |
| `AsyncContextNotStarted` | TestClient issue | Use httpx.AsyncClient for integration tests |

### Log Locations
| Log | Path |
|-----|------|
| Application | `/opt/sentinelwatch/logs/backend.log` |
| Access | `/opt/sentinelwatch/logs/access.log` |
| Error | `/opt/sentinelwatch/logs/error.log` |
| Audit | `/opt/sentinelwatch/logs/audit.log` |
| Nginx Access | `/var/log/nginx/access.log` |
| Nginx Error | `/var/log/nginx/error.log` |
| Systemd | `journalctl -u sentinelwatch-backend` |

---

## Rollback Procedure

```bash
# 1. Stop service
sudo systemctl stop sentinelwatch-backend

# 2. Restore database
gunzip -c /opt/sentinelwatch/backups/sentinelwatch_20261112_120000.sql.gz | \
    psql -h localhost -U sentinelwatch -d sentinelwatch

# 3. Restore config (if changed)
cp /opt/sentinelwatch/config/backend.yaml.backup /opt/sentinelwatch/config/backend.yaml

# 4. Restart
sudo systemctl start sentinelwatch-backend
sudo systemctl status sentinelwatch-backend
```

---

## Security Hardening Checklist

- [ ] Run as non-root user (`sentinelwatch`)
- [ ] TLS 1.2+ only, strong ciphers
- [ ] HSTS enabled
- [ ] Security headers (CSP, X-Frame-Options, etc.)
- [ ] Rate limiting enabled
- [ ] JWT secret from env var (not config file)
- [ ] Database credentials not in config file
- [ ] TLS cert/key readable only by sentinelwatch user
- [ ] Systemd hardening: `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem`
- [ ] Firewall: Only 443/80 (nginx), 5432 (postgres internal), 6379 (redis internal)
- [ ] Audit logging enabled
- [ ] Log rotation configured
- [ ] Regular backup schedule
- [ ] Vulnerability scanning in CI/CD
