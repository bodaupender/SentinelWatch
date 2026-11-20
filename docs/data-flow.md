# SentinelWatch Data Flow

## Overview

This document describes the flow of data through the SentinelWatch system, from endpoint collection to analyst presentation.

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                    ENDPOINT (Agent)                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │ Process      │  │ Service      │  │ Startup      │  │ Event Log    │  │ Config             │   │
│  │ Collector    │  │ Collector    │  │ Collector    │  │ Collector    │  │ Poller             │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────────┬──────────┘   │
│         │                 │                 │                 │                 │              │
│         ▼                 ▼                 ▼                 ▼                 ▼              │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │                        TELEMETRY AGGREGATOR                                             │   │
│  │  • Normalizes data to common schema                                                    │   │
│  │  • Redacts sensitive data (secrets in command lines)                                   │   │
│  │  • Adds metadata (timestamp, agent_id, sequence_num)                                   │   │
│  │  • Batches events (configurable size/interval)                                         │   │
│  │  • Compresses batches (zstd)                                                           │   │
│  └─────────────────────────────────────┬──────────────────────────────────────────────────┘   │
│                                       │                                                         │
│                                       ▼                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │                   HTTPS + AGENT TOKEN TRANSPORT                                        │   │
│  │  • Per-agent bearer token; TLS certificate verification for HTTPS                      │   │
│  │  • Certificate pinning (backend CA)                                                    │   │
│  │  • Automatic retry with exponential backoff                                            │   │
│  │  • Circuit breaker on repeated failures                                                │   │
│  └─────────────────────────────────────┬──────────────────────────────────────────────────┘   │
└───────────────────────────────────────│───────────────────────────────────────────────────────┘
                                        │ HTTPS + bearer token
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                    BACKEND API                                      │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   ┌────────────────────────┐  │
│  │ Ingestion API    │   │ Detection Engine │   │ Alert Manager    │   │ Config Distribution    │  │
│  │ /api/v1/telemetry│   │                  │   │                  │   │ /api/v1/agents/config  │  │
│  └────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘   └───────────┬────────────┘  │
│           │                      │                      │                      │              │
│           ▼                      ▼                      ▼                      ▼              │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                          DATABASE (SQLAlchemy ORM)                                       │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   │  │
│  │  │ agents      │ │ process_    │ │ service_    │ │ startup_    │ │ event_log_      │   │  │
│  │  │             │ │ telemetry   │ │ telemetry   │ │ inventory   │ │ entries         │   │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────┘   │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐   │  │
│  │  │ alerts      │ │ evidence    │ │ rules       │ │ audit_log   │ │ users           │   │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────────────────────────────────┘  │
│           │                      │                      │                      │              │
│           ▼                      ▼                      ▼                      ▼              │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   ┌────────────────────────┐  │
│  │ Tenant SSE Hub   │   │ Metrics          │   │ Audit Logger     │   │ REST polling fallback  │  │
│  │ (in-process      │   │ (Prometheus)     │   │                  │   │                        │  │
│  │ invalidations)   │   │                  │   │                  │   │                        │  │
│  └────────┬─────────┘   └──────────────────┘   └──────────────────┘   └────────────────────────┘  │
└───────────│───────────────────────────────────────────────────────────────────────────────────────┘
            │ SSE invalidation / REST snapshots
            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                    FRONTEND (SOC Dashboard)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │ Auth         │  │ Agent        │  │ Process/     │  │ Alert        │  │ Rules/Audit/       │   │
│  │ Context      │  │ Inventory    │  │ Service View │  │ Console      │  │ Settings           │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────────┬──────────┘   │
│         │                 │                 │                 │                 │              │
│         └─────────────────┴─────────────────┴─────────────────┴─────────────────┘              │
│                                    │                                                            │
│                                    ▼                                                            │
│                         ┌─────────────────────┐                                                │
│                         │   STATE MANAGEMENT  │                                                │
│                         │  (React Query /     │                                                │
│                         │   Zustand / Context)│                                                │
│                         └─────────────────────┘                                                │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Detailed Data Flows

### 1. Agent Startup & Registration

```
Agent Process                          Backend API
     │                                     │
     ├─ Load local config                  │
     ├─ Generate CSR (if no cert)          │
     ├─ POST /agents/register              │
     │     {csr, enrollment_token,         │
     │      machine_guid, hostname,        │
     │      os_version, agent_version}     │
     │                    ──►              │
     │                                     ├─ Validate enrollment token
     │                                     ├─ Verify CSR signature
     │                                     ├─ Sign CSR → client cert
     │                                     ├─ Create agent record
     │                                     ├─ Generate initial config
     │                    ◄───              │
     │     {client_cert, ca_cert,          │
     │      config_signed, config_version} │
     ├─ Store cert in Windows Cert Store   │
     ├─ Apply config                       │
     └─ Start collectors                   │
```

**Data Structures:**
```json
// Registration Request
{
  "csr": "-----BEGIN CERTIFICATE REQUEST-----...",
  "enrollment_token": "swt_abcdef123456...",
  "machine_guid": "{12345678-ABCD-...}",
  "hostname": "DESKTOP-ABC123",
  "os_version": "Windows 10 Pro 22H2 (Build 19045)",
  "agent_version": "1.0.0"
}

// Registration Response
{
  "client_certificate": "-----BEGIN CERTIFICATE-----...",
  "ca_certificate": "-----BEGIN CERTIFICATE-----...",
  "config": {
    "collection_intervals": {
      "process": 5,
      "service": 30,
      "startup": 3600,
      "eventlog": 10,
      "heartbeat": 30
    },
    "batch_size": 100,
    "batch_interval": 5,
    "rules_version": "2024.01.15"
  },
  "config_signature": "MEUCIQD...",
  "config_version": 42
}
```

### 2. Telemetry Collection & Ingestion

#### Process Telemetry
```
Collector (every 30s)                    Backend
     │                                     │
     ├─ psutil.process_iter()              │
     ├─ For each process:                  │
     │   - pid, ppid, name                 │
     │   - cmdline (redacted)              │
     │   - exe path                        │
     │   - username                        │
     │   - create_time                     │
     │   - cpu_percent, memory_percent     │
     │   - connections (IP, port, state)   │
     │   - hash (SHA256 of exe, optional)  │
     ├─ Normalize to schema                │
     ├─ Add metadata:                      │
     │   {agent_id, timestamp, seq_num}    │
     ├─ Batch (max 100, max 5s)            │
     ├─ Compress (zstd)                    │
     ├─ POST /api/v1/telemetry/process     │
     │     {batch: [...], compressed: true}│
     │                    ──►              │
     │                                     ├─ Decompress
     │                                     ├─ Validate each record (Pydantic)
     │                                     ├─ Store in process_telemetry table
     │                                     ├─ Run detection rules
     │                                     ├─ If alert: create alert + evidence
     │                    ◄───              │
     │     {accepted: 98, rejected: 2,     │
     │      alerts_created: 1}             │
```

#### Service Telemetry
```
Collector (every 60s)                    Backend
     │                                     │
     ├─ win32service.EnumServicesStatusEx  │
     ├─ For each service:                  │
     │   - name, display_name              │
     │   - status (running/stopped)        │
     │   - start_type (auto/manual/disabled)│
     │   - binary_path                     │
     │   - service_type                    │
     │   - dependencies                    │
     ├─ Normalize, batch, compress         │
     ├─ POST /api/v1/telemetry/service     │
     │                    ──►              │
     │                                     ├─ Validate, store, detect
     │                    ◄───              │
```

#### Startup Inventory
```
Collector (every 3600s)                  Backend
     │                                     │
     ├─ Registry: HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run
     ├─ Registry: HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run
     ├─ Registry: HKLM\SOFTWARE\WOW6432Node\...\Run
     ├─ Scheduled Tasks (Task Scheduler API)
     ├─ Startup Folder (shell:startup, shell:common startup)
     ├─ WMI Subscriptions (__EventFilter, __FilterToConsumerBinding)
     ├─ For each entry:                    │
     │   - source (registry/task/folder/wmi)│
     │   - name, command, user_context     │
     │   - enabled                         │
     ├─ Normalize, batch, compress         │
     ├─ POST /api/v1/telemetry/startup     │
     │                    ──►              │
```

#### Event Log Collection
```
Collector (continuous, poll every 10s)   Backend
     │                                     │
     ├─ Subscribe to Security, System,     │
     │  Application logs                   │
     ├─ Filter for relevant Event IDs:     │
     │  - 4688 (Process Creation)          │
     │  - 4689 (Process Exit)              │
     │  - 7045 (Service Installed)         │
     │  - 7036 (Service State Change)      │
     │  - 4698 (Scheduled Task Created)    │
     │  - 4699 (Scheduled Task Deleted)    │
     │  - 4700 (Scheduled Task Enabled)    │
     │  - 4701 (Scheduled Task Disabled)   │
     │  - 4702 (Scheduled Task Updated)    │
     ├─ For each event:                    │
     │   - event_id, timestamp, record_id  │
     │   - computer, source, level         │
     │   - message, xml (selective)        │
     │   - extracted fields (PID, cmdline, │
     │     service_name, task_name, etc.)  │
     ├─ Batch, compress                    │
     ├─ POST /api/v1/telemetry/events      │
     │                    ──►              │
```

### 3. Detection Engine Processing

```
Incoming Telemetry Record
         │
         ▼
┌──────────────────────────────────────────┐
│        RULE EVALUATION PIPELINE          │
├──────────────────────────────────────────┤
│                                          │
│  1. RULE MATCHING                        │
│     For each enabled rule:               │
│       - Check rule.applies_to (telemetry │
│         type: process/service/startup/   │
│         event)                           │
│       - Evaluate condition (CEL expr)    │
│       - If match: create Finding         │
│                                          │
│  2. FINDING ENRICHMENT                   │
│     - Add MITRE ATT&CK tags              │
│     - Add severity (critical/high/med/low)│
│     - Add context (process tree, user,   │
│       network connections)               │
│     - Lookup threat intel (optional)     │
│                                          │
│  3. ALERT CREATION                       │
│     - Group findings by correlation key  │
│       (agent_id + rule_id + time window) │
│     - Deduplicate (same alert in 1h)     │
│     - Create Alert record                │
│     - Create Evidence snapshot           │
│       (raw telemetry that triggered)     │
│                                          │
│  4. DASHBOARD INVALIDATION               │
│     - Publish tenant-scoped SSE notice   │
│     - Client refreshes authorized REST   │
│       snapshots; polling is the fallback │
│                                          │
└──────────────────────────────────────────┘
```

### 4. Alert Triage Flow (Dashboard)

```
Analyst Action                          Backend
     │                                     │
     ├─ GET /api/v1/alerts?status=new      │
     │                    ◄───              │
     │     {alerts: [...]}                 │
     ├─ GET /api/v1/alerts/{id}/evidence   │
     │                    ◄───              │
     │     {process_tree, cmdline,         │
     │      network_conns, file_hashes}    │
     ├─ POST /api/v1/alerts/{id}/triage    │
     │     {status: "investigating",       │
     │      assignee: "analyst_john",      │
     │      notes: "Suspicious..."}        │
     │                    ──►              │
     │                                     ├─ Update alert
     │                                     ├─ Audit log entry
     │                    ◄───              │
     │     {alert: {...}}                  │
     ├─ (later) POST /api/v1/alerts/{id}/  │
     │     resolve                         │
     │     {status: "resolved",            │
     │      resolution: "true_positive",   │
     │      notes: "Confirmed malware"}    │
     │                    ──►              │
```

### 5. Configuration Distribution

```
Backend (admin action)                   Agent
     │                                     │
     ├─ Admin updates config via UI        │
     ├─ Backend signs new config           │
     │     (Ed25519, includes version)     │
     ├─ Config version incremented         │
     │                                     │
     │                         Poll (config_interval)    │
     │                         GET /api/v1/agents/config │
     │                                              ──►  │
     │                         {config, signature,       │
     │                          version} ◄───            │
     │                                     ├─ Verify signature
     │                                     ├─ Check version > current
     │                                     ├─ Apply new config
     │                                     ├─ Restart collectors if needed
```

### 6. Health & Heartbeat

```
Agent (every 60s)                        Backend
     │                                     │
     ├─ Collect health metrics:            │
     │   - cpu_percent, memory_mb          │
     │   - disk_free_gb                    │
     │   - network_bytes_sent/recv         │
     │   - collector_status (ok/error)     │
     │   - last_telemetry_sent             │
     │   - queue_depth (unsent batches)    │
     ├─ POST /api/v1/agents/heartbeat      │
     │     {health: {...}, version: "1.0.0"}│
     │                    ──►              │
     │                                     ├─ Update agent.last_seen
     │                                     ├─ Update agent.health
     │                                     ├─ If stale config: include in response
     │                    ◄───              │
     │     {config_update_available: bool} │
```

## Data Models

### Process Telemetry Record
```json
{
  "agent_id": "agent_abc123",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "sequence": 1452,
  "pid": 4521,
  "ppid": 3100,
  "name": "powershell.exe",
  "cmdline": "powershell.exe -EncodedCommand [REDACTED]",
  "exe": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
  "username": "DESKTOP-ABC\\user",
  "create_time": "2024-01-15T10:29:45.000Z",
  "cpu_percent": 2.5,
  "memory_percent": 1.2,
  "memory_rss_mb": 45,
  "connections": [
    {"local_ip": "192.168.1.50", "local_port": 54321, "remote_ip": "203.0.113.10", "remote_port": 443, "status": "ESTABLISHED"}
  ],
  "exe_sha256": "a1b2c3d4...",
  "integrity_level": "Medium"
}
```

### Service Telemetry Record
```json
{
  "agent_id": "agent_abc123",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "sequence": 1453,
  "name": "SentinelWatchAgent",
  "display_name": "SentinelWatch Monitoring Agent",
  "status": "RUNNING",
  "start_type": "AUTO_START",
  "binary_path": "C:\\Program Files\\SentinelWatch\\agent.exe",
  "service_type": "WIN32_OWN_PROCESS",
  "dependencies": ["Tcpip", "AfD"],
  "account": "LocalSystem",
  "exe_sha256": "f1e2d3c4..."
}
```

### Startup Inventory Record
```json
{
  "agent_id": "agent_abc123",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "sequence": 1454,
  "source": "registry_hklm_run",
  "name": "OneDrive",
  "command": "\"C:\\Users\\user\\AppData\\Local\\Microsoft\\OneDrive\\OneDrive.exe\" /background",
  "user_context": "DESKTOP-ABC\\user",
  "enabled": true,
  "exe_sha256": "b2c3d4e5..."
}
```

### Event Log Record
```json
{
  "agent_id": "agent_abc123",
  "timestamp": "2024-01-15T10:30:00.123Z",
  "sequence": 1455,
  "event_id": 4688,
  "record_id": 12345678,
  "source": "Microsoft-Windows-Security-Auditing",
  "level": "Information",
  "computer": "DESKTOP-ABC",
  "message": "A new process has been created...",
  "extracted": {
    "subject_user": "DESKTOP-ABC\\user",
    "new_process_id": 4521,
    "new_process_name": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    "command_line": "powershell.exe -EncodedCommand [REDACTED]",
    "parent_process_id": 3100,
    "parent_process_name": "C:\\Windows\\System32\\cmd.exe",
    "token_elevation_type": "TokenElevationTypeDefault",
    "mandatory_label": "Medium Mandatory Level"
  }
}
```

### Alert Record
```json
{
  "id": "alert_xyz789",
  "created_at": "2024-01-15T10:30:05.000Z",
  "updated_at": "2024-01-15T10:35:00.000Z",
  "agent_id": "agent_abc123",
  "rule_id": "rule_suspicious_powershell",
  "rule_name": "Suspicious PowerShell - Encoded Command",
  "severity": "high",
  "status": "new",
  "mitre_techniques": ["T1059.001", "T1027"],
  "finding_count": 1,
  "correlation_key": "agent_abc123:rule_suspicious_powershell:2024-01-15T10",
  "summary": "PowerShell with encoded command executed by user on DESKTOP-ABC",
  "evidence_ref": "evidence_abc123"
}
```

### Evidence Record
```json
{
  "id": "evidence_abc123",
  "alert_id": "alert_xyz789",
  "created_at": "2024-01-15T10:30:05.000Z",
  "telemetry_type": "process",
  "raw_records": [
    {"pid": 4521, "name": "powershell.exe", "cmdline": "...", "...": "..."}
  ],
  "enrichment": {
    "process_tree": [
      {"pid": 3100, "name": "cmd.exe", "cmdline": "cmd.exe", "children": [4521]},
      {"pid": 4521, "name": "powershell.exe", "cmdline": "...", "children": []}
    ],
    "network_connections": [...],
    "file_hashes": {"sha256": "a1b2c3d4..."},
    "threat_intel": {"malicious": false, "suspicious": true}
  }
}
```

## Data Retention Policies

| Data Type | Hot Storage | Cold Storage | Deletion |
|-----------|-------------|--------------|----------|
| Process telemetry | 7 days | 30 days | Auto-purge |
| Service telemetry | 30 days | 90 days | Auto-purge |
| Startup inventory | 90 days | 1 year | Auto-purge |
| Event log entries | 30 days | 1 year | Auto-purge |
| Alerts | 1 year | 7 years | Manual only |
| Evidence | 1 year | 7 years | Manual only |
| Audit logs | 7 years | Permanent | Never |
| Agent certificates | 90 days | N/A | Auto-renew |

## Data Integrity & Consistency

### Telemetry Ordering
- Each agent maintains a monotonically increasing `sequence` number per telemetry type
- Backend validates sequence gaps (alert on gap > 100)
- Timestamps are UTC with millisecond precision

### Exactly-Once Processing
- Agent tracks acknowledged sequence numbers
- Backend returns `last_acknowledged_sequence` in response
- Agent resends unacknowledged batches on restart

### Schema Evolution
- All telemetry schemas versioned (v1, v2, ...)
- Backend accepts multiple versions simultaneously
- Agents upgrade to latest schema on config update
- Breaking changes require coordinated rollout

## Error Handling & Dead Letter

```
Ingestion Error                    Handling
─────────────────                  ────────
Validation failure (Pydantic)      → Reject single record, continue batch
                                   → Log with error details
                                   → Increment rejected counter

Database error (transient)         → Retry with exponential backoff (3x)
                                   → Circuit breaker after 5 failures
                                   → Alert on-call if persistent

Database error (permanent)         → Dead letter queue (separate table)
                                   → Alert with details
                                   → Manual intervention required

Agent certificate expired          → Reject with 401 + specific code
                                   → Agent triggers re-enrollment

Rate limit exceeded                → 429 with Retry-After header
                                   → Agent backs off exponentially
```

## Monitoring & Observability

### Key Metrics
| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| `agent.telemetry.ingested` | Backend | Drop > 50% for 5m |
| `agent.telemetry.rejected` | Backend | > 1% of ingested |
| `agent.heartbeat.missing` | Backend | > 3 missed (3m) |
| `detection.rules.evaluated` | Backend | N/A |
| `detection.alerts.created` | Backend | Spike > 3σ |
| `agent.health.cpu_percent` | Agent | > 80% for 5m |
| `agent.health.memory_mb` | Agent | > 500MB |
| `agent.queue.depth` | Agent | > 1000 batches |

### Distributed Tracing
- Each telemetry batch gets `trace_id` (UUID)
- Propagated through ingestion → detection → alert creation
- Correlated in logs via `trace_id`
- OpenTelemetry compatible (future)
