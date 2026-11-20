# SentinelWatch Monitoring & Operations Guide

**Version:** 1.0
**Date:** 2026-11-12

---

## Overview

This guide covers monitoring, alerting, and operational procedures for the SentinelWatch platform in production.

---

## Health Checks

### Backend Health Endpoints

| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `GET /health` | Basic liveness | `{"status": "healthy", "timestamp": "...", "version": "..."}` |
| `GET /ready` | Readiness (DB, deps) | `{"status": "ready", "checks": {...}}` |
| `GET /health/detailed` | Detailed diagnostics | Component-level status |

### Expected Response Format
```json
{
  "status": "healthy",
  "timestamp": "2026-11-12T10:00:00.000Z",
  "version": "0.1.0",
  "checks": {
    "database": "healthy",
    "redis": "healthy",
    "agent_ingestion": "healthy"
  }
}
```

---

## Key Metrics to Monitor

### Backend Metrics (Prometheus)

| Metric | Type | Description | Alert Threshold |
|--------|------|-------------|-----------------|
| `http_requests_total` | Counter | Total HTTP requests by endpoint/method/status | > 1000/min sustained |
| `http_request_duration_seconds` | Histogram | Request latency by endpoint | p95 > 1s |
| `http_requests_errors_total` | Counter | 5xx errors by endpoint | > 1% of requests |
| `db_connections_active` | Gauge | Active DB connections | > 80% of pool |
| `db_query_duration_seconds` | Histogram | Database query latency | p95 > 500ms |
| `agent_heartbeat_total` | Counter | Agent heartbeats received | < expected agents/min |
| `telemetry_ingested_total` | Counter | Telemetry records ingested | Drop > 50% |
| `alert_generated_total` | Counter | Alerts created | > 3σ above baseline |
| `alert_resolved_total` | Counter | Alerts resolved | < 50% of generated |
| `detection_evaluation_duration_seconds` | Histogram | Rule evaluation time | > 1s |
| `jwt_tokens_issued_total` | Counter | JWT tokens issued | Spike > 10x |
| `rate_limit_exceeded_total` | Counter | Rate limit hits | > 100/min |

### Agent Fleet Metrics

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `agent_online_count` | Agents with heartbeat < 5min | < 90% of registered |
| `agent_stale_count` | Agents with heartbeat > 15min | > 10% of registered |
| `agent_offline_count` | Agents with heartbeat > 1hr | > 5% of registered |
| `telemetry_batch_size` | Records per batch | > 500 avg |
| `telemetry_latency_seconds` | Ingestion to DB | > 30s p95 |

### Frontend Metrics

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `frontend_load_time_seconds` | Page load time | > 3s |
| `frontend_js_errors_total` | JavaScript errors | > 10/min |
| `api_request_duration_seconds` | API latency from browser | > 2s p95 |
| `websocket_disconnects_total` | WS disconnects | > 10/min |

---

## Alerting Rules

### Critical Alerts (Page Immediately)

```yaml
# Critical: Backend Down
- alert: BackendDown
  expr: up{job="sentinelwatch-backend"} == 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "SentinelWatch backend is down"
    description: "Backend has been down for more than 1 minute"

# Critical: Database Down
- alert: DatabaseDown
  expr: up{job="postgresql"} == 0
  for: 30s
  labels:
    severity: critical
  annotations:
    summary: "PostgreSQL database is down"

# Critical: No Agent Heartbeats
- alert: NoAgentHeartbeats
  expr: rate(agent_heartbeat_total[5m]) == 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "No agent heartbeats received"
    description: "No agents have checked in for 5 minutes"

# Critical: High Error Rate
- alert: HighErrorRate
  expr: rate(http_requests_errors_total[5m]) / rate(http_requests_total[5m]) > 0.05
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "High API error rate (>5%)"
```

### Warning Alerts (Page During Business Hours)

```yaml
# Warning: High Latency
- alert: HighLatency
  expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High API latency (p95 > 1s)"

# Warning: High Agent Offline Rate
- alert: HighAgentOfflineRate
  expr: agent_offline_count / agent_registered_count > 0.1
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "High agent offline rate (>10%)"

# Warning: Database Connection Pool Exhaustion
- alert: DBConnectionPoolExhaustion
  expr: db_connections_active / db_connections_max > 0.8
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Database connection pool > 80% utilized"

# Warning: High Alert Volume
- alert: HighAlertVolume
  expr: rate(alert_generated_total[5m]) > 100
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High alert generation rate (>100/min)"

# Warning: Disk Space
- alert: DiskSpaceLow
  expr: (disk_free_bytes / disk_total_bytes) < 0.1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Disk space < 10% free"
```

### Info Alerts (Log Only)

```yaml
# Info: New Agent Registered
- alert: NewAgentRegistered
  expr: increase(agent_registered_total[1h]) > 0
  labels:
    severity: info
  annotations:
    summary: "New agent registered"

# Info: Detection Rule Promoted
- alert: RulePromoted
  expr: increase(rule_promoted_total[1h]) > 0
  labels:
    severity: info
  annotations:
    summary: "Detection rule promoted to active"
```

---

## Log Monitoring

### Key Log Patterns to Monitor

| Pattern | Log Level | Source | Action |
|---------|-----------|--------|--------|
| `unhandled_exception` | ERROR | Backend | Alert immediately |
| `database_health_check_failed` | ERROR | Backend | Alert immediately |
| `login_failed` | WARNING | Auth | Correlate with brute force |
| `agent_registration_failed` | WARNING | Agent Comm | Investigate agent |
| `detection_rule_test_failed` | WARNING | Detection | Review rule |
| `audit_log_write_failed` | ERROR | Audit | Alert immediately |
| `certificate_expiring` | WARNING | TLS | Renew within 30 days |

### Log Aggregation Queries

```sql
-- Error rate by endpoint (last hour)
SELECT endpoint, COUNT(*) as error_count
FROM logs
WHERE level = 'ERROR' AND timestamp > NOW() - INTERVAL '1 hour'
GROUP BY endpoint
ORDER BY error_count DESC;

-- Agent heartbeat gaps
SELECT agent_id, MAX(timestamp) as last_heartbeat
FROM agent_heartbeats
GROUP BY agent_id
HAVING MAX(timestamp) < NOW() - INTERVAL '15 minutes';

-- Alert resolution time
SELECT
  percentile_cont(0.5) WITHIN GROUP (ORDER BY resolved_at - created_at) as median_resolution,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY resolved_at - created_at) as p95_resolution
FROM alerts
WHERE resolved_at IS NOT NULL
  AND created_at > NOW() - INTERVAL '24 hours';
```

---

## Dashboard Panels (Grafana)

### System Overview Dashboard

| Panel | Query | Visualization |
|-------|-------|---------------|
| Request Rate | `rate(http_requests_total[5m])` | Time series |
| Error Rate | `rate(http_requests_errors_total[5m]) / rate(http_requests_total[5m])` | Gauge |
| P95 Latency | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))` | Time series |
| Active Agents | `agent_online_count` | Stat |
| Alert Rate | `rate(alert_generated_total[5m])` | Time series |
| DB Connections | `db_connections_active / db_connections_max` | Gauge |

### Agent Fleet Dashboard

| Panel | Query | Visualization |
|-------|-------|---------------|
| Online Agents | `agent_online_count` | Stat |
| Agent Status Distribution | `count by (status) (agent_status)` | Pie chart |
| Heartbeat Rate | `rate(agent_heartbeat_total[5m])` | Time series |
| Telemetry Ingestion | `rate(telemetry_ingested_total[5m])` | Time series |

### Alert Operations Dashboard

| Panel | Query | Visualization |
|-------|-------|---------------|
| Open Alerts by Severity | `count by (severity) (alert_status{status="open"})` | Bar chart |
| Alert Resolution Time | `histogram_quantile(0.5, rate(alert_resolution_duration_seconds_bucket[1h]))` | Time series |
| Triage Rate | `rate(alert_triaged_total[5m])` | Time series |
| False Positive Rate | `rate(alert_resolved_total{resolution="false_positive"}[1h]) / rate(alert_resolved_total[1h])` | Gauge |

---

## Log Collection & Analysis

### Centralized Logging (ELK/Loki)

```yaml
# Loki configuration for SentinelWatch
scrape_configs:
  - job_name: sentinelwatch-backend
    static_configs:
      - targets: ['localhost:9080']  # Loki promtail
    pipeline_stages:
      - json:
          expressions:
            level: level
            message: message
            timestamp: timestamp
            request_id: request_id
            user_id: user_id
            endpoint: endpoint
```

### Key Dashboard Queries

```logql
# Error rate by endpoint
sum by (endpoint) (rate({job="sentinelwatch-backend"} |= "error" [5m]))

# Slow queries
{job="sentinelwatch-backend"} | json | duration > 1

# Authentication failures
{job="sentinelwatch-backend"} |= "login_failed"

# Agent registration failures
{job="sentinelwatch-backend"} |= "registration_failed"
```

---

## Incident Response Procedures

### Runbook: Backend Down

1. **Verify**: Check `curl https://api.domain.com/health`
2. **Check Service**: `systemctl status sentinelwatch-backend`
3. **Check Logs**: `journalctl -u sentinelwatch-backend -n 100`
4. **Check Database**: `systemctl status postgresql`
5. **Restart**: `systemctl restart sentinelwatch-backend`
6. **Verify**: `curl https://api.domain.com/health`

### Runbook: High Agent Offline Rate

1. **Check Agent Count**: `curl -H "Authorization: Bearer $TOKEN" https://api.domain.com/api/v1/agents/`
2. **Check Network**: Verify backend accessibility from agent network
3. **Check Agent Logs**: Sample agent logs for connection errors
4. **Check Backend Logs**: `grep "agent_heartbeat" /var/log/sentinelwatch/backend.log`
4. **Verify Certificates**: Check agent certificate expiration

### Runbook: High Alert Volume

1. **Identify Source**: `curl -H "Authorization: Bearer $TOKEN" "https://api.domain.com/api/v1/alerts/stats/summary"`
2. **Check Detection Rules**: Review recently promoted rules
3. **Check False Positives**: `curl -H "Authorization: Bearer $TOKEN" "https://api.domain.com/api/v1/alerts/?status=false_positive"`
4. **Tune Rules**: Demote noisy rules or add suppression

---

## Maintenance Procedures

### Daily
- [ ] Verify all agents checking in
- [ ] Review alert queue for aging alerts (>24h)
- [ ] Check disk space on all servers
- [ ] Verify backup completed

### Weekly
- [ ] Review alert resolution metrics
- [ ] Check certificate expiration (30-day warning)
- [ ] Review false positive rate trends
- [ ] Verify backup completion
- [ ] Check for security updates

### Monthly
- [ ] Rotate JWT secret (if compromised)
- [ ] Review and rotate API keys
- [ ] Update detection rules
- [ ] Review and prune old audit logs
- [ ] Test backup restoration
- [ ] Review capacity planning

### Quarterly
- [ ] Penetration testing
- [ ] Certificate renewal
- [ ] Disaster recovery drill
- [ ] Security configuration review
- [ ] Dependency vulnerability scan

---

## Escalation Contacts

| Role | Contact | Escalation Time |
|------|---------|-----------------|
| On-call Engineer | +1-XXX-XXX-XXXX | Immediate (Critical) |
| Team Lead | +1-XXX-XXX-XXXX | 15 min (Critical), 1hr (Warning) |
| Security Team | security@company.com | 30 min (Security) |
| DBA | dba@company.com | 30 min (DB Issues) |
| Network Team | network@company.com | 30 min (Network) |

---

## Runbook Templates

### Template: New Alert Type Investigation

```
## Alert Investigation: [Alert Name]

**Trigger**: [What caused the alert]
**Severity**: [Critical/Warning/Info]
**First Seen**: [Timestamp]
**Affected Systems**: [List]

### Investigation Steps:
1. [ ] Check alert details in dashboard
2. [ ] Review associated evidence
3. [ ] Check related alerts
4. [ ] Query related telemetry
5. [ ] Determine root cause

### Findings:
- **Root Cause**: [Description]
- **Impact**: [Systems/users affected]
- **Confidence**: [High/Medium/Low]

### Action Taken:
- [ ] Triage status updated
- [ ] Evidence documented
- [ ] Stakeholders notified
- [ ] Remediation initiated

### Resolution:
- **Status**: [Resolved/Suppressed/Escalated]
- **Resolution Notes**: [Details]
- **Prevention**: [Steps to prevent recurrence]
```
