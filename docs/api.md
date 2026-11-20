# SentinelWatch API Documentation

## Overview

The SentinelWatch API provides a RESTful interface for managing Windows endpoint monitoring, telemetry ingestion, alert management, and detection rule management.

**Base URL**: `https://api.sentinelwatch.local/api/v1`

## Authentication

All API endpoints (except `/health` and `/api/v1/auth/login`) require authentication via JWT Bearer token.

### Authentication Flow

1. **Login**: `POST /api/v1/auth/login` with username/password
2. **Access Token**: Short-lived (15 min default) JWT for API access
3. **Refresh Token**: Long-lived (7 days default) stored in HttpOnly cookie
4. **Token Refresh**: `POST /api/v1/auth/refresh` with refresh token

### Headers

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

## Rate Limiting

The backend enforces configured per-IP token-bucket limits for general API traffic, agent traffic, authentication routes and agent registration. Rejections return HTTP 429 and a `Retry-After` header. Buckets are in memory and local to each server process; multi-worker or replicated deployments must enforce shared limits at a trusted gateway. The application uses the direct connection peer address and does not trust arbitrary `X-Forwarded-For` headers.

## Error Responses

All errors follow RFC 7807 Problem Details format:

```json
{
  "type": "https://tools.ietf.org/html/rfc7231#section-6.5.1",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Invalid or expired token",
  "instance": "/api/v1/agents"
}
```

## API Endpoints

### Live Dashboard Updates

#### GET /api/v1/events/stream

Open an authenticated Server-Sent Events stream for the selected organization. Send `Authorization: Bearer <access_token>` and, when the user belongs to more than one organization, `X-Organization-ID: <organization_id>`. The stream emits a `ready` event on connect and an `invalidate` event after relevant agent, telemetry, or alert changes. Event data is intentionally empty; clients refetch authorized REST snapshots for the actual records.

The browser reconnects with exponential backoff and invalidates cached queries after reconnect. Existing REST polling remains the fallback if the stream is unavailable. The current notification hub is in-process; multi-worker deployments may miss notifications published by another worker, so polling remains necessary.

### Agent Enrollment

Enrollment tokens are returned in full only when created, stored as a hash, single-use by default, and expire after 7 days by default. Administrators can set a lifetime from 1 to 30 days and can configure a controlled maximum use count. Editing a token cannot extend its expiry beyond 30 days from the time of the update.

### Authentication

#### POST /api/v1/auth/login
Authenticate user and obtain tokens.

**Request:**
```json
{
  "username": "analyst",
  "password": "secure_password"
}
```

**Response (200):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### POST /api/v1/auth/refresh
Refresh access token using refresh token.

**Request:**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

#### POST /api/v1/auth/logout
Logout and invalidate refresh token.

#### GET /api/v1/auth/me
Get current user information.

### Agent Management

#### POST /api/v1/agents/register
Register a new agent endpoint.

**Request:**
```json
{
  "hostname": "DESKTOP-001",
  "machine_guid": "12345678-ABCD-EF12-3456-7890ABCDEF12",
  "os_version": "Windows 10 Pro 22H2",
  "agent_version": "0.1.0",
  "enrollment_token": "swt_abc123...",
  "tags": "workstation,finance"
}
```

#### GET /api/v1/agents
List all registered agents.

**Query Parameters:**
- `status`: Filter by status (online, offline, stale)
- `search`: Search hostname
- `skip`: Pagination offset
- `limit`: Page size (max 1000)

#### GET /api/v1/agents/{agent_id}
Get agent details including health data.

#### GET /api/v1/agents/{agent_id}/config
Get agent configuration.

#### PUT /api/v1/agents/{agent_id}/config
Update agent configuration.

#### DELETE /api/v1/agents/{agent_id}
Unenroll agent.

#### GET /api/v1/agents/{agent_id}/health
Get agent health metrics.

### Telemetry

#### GET /api/v1/telemetry/processes
List process telemetry with filtering.

**Query Parameters:**
- `agent_id`: Filter by agent
- `name`: Filter by process name
- `username`: Filter by username
- `pid`: Filter by PID
- `start_time` / `end_time`: Time range
- `skip`, `limit`: Pagination
- `sort`, `order`: Sorting

#### GET /api/v1/telemetry/services
List service telemetry.

#### GET /api/v1/telemetry/startup
List startup inventory.

#### GET /api/v1/telemetry/events
List Windows event log entries.

### Alerts

#### GET /api/v1/alerts
List alerts with filtering.

**Query Parameters:**
- `agent_id`, `status`, `severity`, `rule_id`
- `search`: Search in summary/description
- `start_time`, `end_time`: Time range
- Pagination and sorting

#### GET /api/v1/alerts/{alert_id}
Get alert details.

#### GET /api/v1/alerts/{alert_id}/evidence
Get alert evidence.

#### POST /api/v1/alerts/{alert_id}/triage
Triage an alert.

**Request:**
```json
{
  "status": "investigating",
  "assignee": "analyst_john",
  "notes": "Investigating suspicious PowerShell activity"
}
```

#### POST /api/v1/alerts/{alert_id}/resolve
Resolve an alert.

**Request:**
```json
{
  "resolution": "true_positive",
  "notes": "Confirmed malicious PowerShell execution"
}
```

#### POST /api/v1/alerts/bulk/triage
Bulk triage multiple alerts.

### Detection Rules

#### GET /api/v1/rules
List detection rules (custom + builtin).

#### GET /api/v1/rules/builtin
List built-in detection rules.

#### GET /api/v1/rules/{rule_id}
Get rule details.

#### POST /api/v1/rules
Create custom detection rule (admin).

#### PUT /api/v1/rules/{rule_id}
Update custom rule (admin).

#### POST /api/v1/rules/{rule_id}/test
Test rule against sample telemetry.

#### POST /api/v1/rules/{rule_id}/promote
Promote rule to active (admin).

#### POST /api/v1/rules/{rule_id}/demote
Demote rule to staging (admin).

#### DELETE /api/v1/rules/{rule_id}
Delete custom rule (admin).

### Reports

#### GET /api/v1/reports/alerts
Generate alert report.

#### GET /api/v1/reports/endpoints
Generate endpoint inventory report.

#### GET /api/v1/reports/investigation/{alert_id}
Export investigation data.

#### GET /api/v1/reports/alerts/export
Export alerts as CSV.

### Suppressions

#### GET /api/v1/suppressions
List suppression rules.

#### POST /api/v1/suppressions
Create suppression rule (admin).

#### PUT /api/v1/suppressions/{id}
Update suppression rule (admin).

#### DELETE /api/v1/suppressions/{id}
Delete suppression rule (admin).

### Audit Logs

#### GET /api/v1/audit
List audit log entries.

#### GET /api/v1/audit/export/csv
Export audit logs as CSV.

### Agent Communication

#### POST /api/v1/agent/v1/register
Register new agent.

#### POST /api/v1/agent/v1/heartbeat
Agent heartbeat.

#### POST /api/v1/agent/v1/telemetry
Submit telemetry batch.

#### POST /api/v1/agent/v1/config/poll
Agent configuration polling.

#### GET /api/v1/agent/v1/health
Get agent health metrics.

## Data Models

### Alert
```json
{
  "id": "string",
  "agent_id": "string",
  "rule_id": "string",
  "rule_name": "string",
  "severity": "critical|high|medium|low|info",
  "status": "new|investigating|true_positive|false_positive|benign|resolved|suppressed",
  "mitre_techniques": ["T1059.001"],
  "mitre_tactics": ["TA0002"],
  "correlation_key": "string",
  "finding_count": 1,
  "summary": "string",
  "description": "string",
  "evidence_id": "string",
  "assignee": "string",
  "triage_notes": "string",
  "triaged_at": "datetime",
  "resolution": "true_positive|false_positive|benign|suppressed",
  "resolution_notes": "string",
  "resolved_at": "datetime",
  "resolved_by": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### Agent
```json
{
  "id": "string",
  "hostname": "string",
  "machine_guid": "string",
  "os_version": "string",
  "agent_version": "string",
  "ip_address": "string",
  "status": "online|offline|stale|unregistered",
  "last_seen": "datetime",
  "last_heartbeat": "datetime",
  "config_version": "integer",
  "tags": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### ProcessTelemetry
```json
{
  "id": "string",
  "agent_id": "string",
  "collected_at": "datetime",
  "sequence": "integer",
  "pid": "integer",
  "ppid": "integer",
  "name": "string",
  "cmdline": "string",
  "exe": "string",
  "username": "string",
  "create_time": "datetime",
  "cpu_percent": "number",
  "memory_percent": "number",
  "memory_rss_mb": "number",
  "connections": "array",
  "exe_sha256": "string",
  "integrity_level": "string"
}
```

### ServiceTelemetry
```json
{
  "id": "string",
  "agent_id": "string",
  "collected_at": "datetime",
  "sequence": "integer",
  "name": "string",
  "display_name": "string",
  "status": "RUNNING|STOPPED|PAUSED|START_PENDING|STOP_PENDING|CONTINUE_PENDING|PAUSE_PENDING",
  "start_type": "AUTO|MANUAL|DISABLED|DELAYED_AUTO",
  "binary_path": "string",
  "service_type": "string",
  "dependencies": "array",
  "account": "string",
  "exe_sha256": "string"
}
```

### StartupInventory
```json
{
  "id": "string",
  "agent_id": "string",
  "collected_at": "datetime",
  "sequence": "integer",
  "source": "registry_run|registry_runonce|startup_folder|scheduled_task|wmi_subscription|service",
  "name": "string",
  "command": "string",
  "user_context": "string",
  "enabled": "boolean",
  "exe_sha256": "string"
}
```

### EventLogEntry
```json
{
  "id": "string",
  "agent_id": "string",
  "collected_at": "datetime",
  "sequence": "integer",
  "event_id": "integer",
  "record_id": "integer",
  "source": "string",
  "level": "string",
  "computer": "string",
  "message": "string",
  "extracted": {},
  "event_timestamp": "datetime"
}
```

### Alert
```json
{
  "id": "string",
  "agent_id": "string",
  "rule_id": "string",
  "rule_name": "string",
  "severity": "critical|high|medium|low|info",
  "status": "new|investigating|true_positive|false_positive|benign|resolved|suppressed",
  "mitre_techniques": ["T1059.001"],
  "mitre_tactics": ["TA0002"],
  "correlation_key": "string",
  "finding_count": 1,
  "summary": "string",
  "description": "string",
  "evidence_id": "string",
  "assignee": "string",
  "triage_notes": "string",
  "triaged_at": "datetime",
  "resolution": "true_positive|false_positive|benign|suppressed",
  "resolution_notes": "string",
  "resolved_at": "datetime",
  "resolved_by": "string",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

### Evidence
```json
{
  "id": "string",
  "alert_id": "string",
  "telemetry_type": "process|service|startup|eventlog",
  "raw_records": [],
  "process_tree": [],
  "network_connections": [],
  "file_hashes": {},
  "threat_intel": {},
  "collected_at": "datetime",
  "size_bytes": "integer"
}
```

### DetectionRule
```json
{
  "rule_id": "string",
  "rule_name": "string",
  "description": "string",
  "rule_type": "condition|correlation|threshold",
  "category": "process|service|startup|eventlog|correlation",
  "severity": "critical|high|medium|low|info",
  "confidence": 0.0-100.0,
  "condition": "string",
  "condition_version": 1,
  "mitre_techniques": ["T1059.001"],
  "mitre_tactics": ["TA0002"],
  "evidence_requirements": ["field1", "field2"],
  "investigation_guidance": "string",
  "version": 1,
  "previous_rule_id": "string",
  "status": "active|draft|disabled|deprecated",
  "times_executed": 0,
  "times_triggered": 0,
  "last_triggered": "datetime",
  "duplicate_window_seconds": 3600
}
```

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request - Invalid request data |
| 401 | Unauthorized - Invalid or missing authentication |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource not found |
| 409 | Conflict - Resource conflict |
| 422 | Unprocessable Entity - Validation error |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error |

## Rate Limiting Headers

Rejected requests return `Retry-After` with the number of seconds to wait before retrying. Limits are keyed by direct peer IP, held in memory per server process, and are not shared across workers or replicas. A trusted gateway must enforce shared limits in multi-worker deployments.

## WebSocket (Future)

Real-time updates will be available via WebSocket at `/ws/v1` for:
- New alerts
- Endpoint health updates
- Agent status changes
- Detection rule updates

## SDK Examples

### Python
```python
import httpx

client = httpx.AsyncClient(base_url="https://api.sentinelwatch.local/api/v1")

# Login
response = await client.post("/auth/login", data={"username": "user", "password": "pass"})
tokens = response.json()

# Use access token
client.headers["Authorization"] = f"Bearer {tokens['access_token']}"

# List alerts
alerts = await client.get("/alerts", params={"severity": "high"})
```

### cURL
```bash
# Login
curl -X POST https://api.sentinelwatch.local/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=analyst&password=secret"

# Get alerts
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.sentinelwatch.local/api/v1/alerts?severity=high&limit=50"
```

## Changelog

### v0.1.0 (Current)
- Initial API release
- Authentication (JWT + refresh tokens)
- Agent management
- Telemetry ingestion
- Alert management with lifecycle
- Detection rules (builtin + custom)
- Reporting and exports
- Audit logging
- Agent communication protocol
# Agent credentials

Agent registration returns a short-lived access token (15 minutes) and an opaque refresh token (90-day sliding lifetime). Agents call `POST /api/v1/agent/v1/token/refresh` with `{"refresh_token":"…"}` before retrying an API request after an access-token 401. Refresh tokens rotate on use; the prior value is invalidated, and only a hash is stored by the backend. Re-enrollment rotates the credential generation. Agent refresh tokens are independent from user login refresh tokens.

On the endpoint, failed telemetry uploads are requeued in memory up to `batching.max_pending_records` (default 10,000). If full, the oldest records are dropped and logged. The queue does not persist across an agent process restart.

## Endpoint report counts

`GET /api/v1/reports/endpoints` preserves `total_endpoints` as the number of non-deleted inventory records and adds `enrolled_endpoints` and `unregistered_endpoints`. An endpoint counts as enrolled only while its stored credential generation is current and not revoked. Metadata-only entries do not count as enrolled and do not indicate that an endpoint is online or sending telemetry.
