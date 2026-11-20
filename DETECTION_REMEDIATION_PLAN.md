# SentinelWatch Detection Engine Remediation Plan

**Date**: 2025-11-15
**Status**: In Progress

---

## Phase 1: Critical - Stable Alert IDs & Deduplication (Week 1)

### 1.1 Stable Alert IDs
**File:** `backend/src/sentinelwatch_backend/api/v1/agent_communication.py`

**Current:** `alert-{rule_id}-{timestamp}` - not deterministic
**Target:** `sha256(rule_id + entity_id + time_window_start)[:16]`

**Implementation:**
```python
def generate_stable_alert_id(rule_id: str, entity_id: str, time_window_start: datetime) -> str:
    """Generate deterministic alert ID from rule + entity + time window."""
    import hashlib
    window_start = time_window_start.isoformat()
    key = f"{rule_id}|{entity_id}|{window_start}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

### 1.2 Alert Deduplication
**File:** `backend/src/sentinelwatch_backend/models/alert.py` + `agent_communication.py`

**Add to Alert model:**
```python
# Add deduplication key
dedup_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
dedup_window_seconds: Mapped[int] = mapped_column(Integer, default=3600)
```

**In alert creation:**
```python
# Generate dedup key
dedup_key = f"{rule_id}|{entity_id}|{window_start_timestamp}"
# Check existing
existing = await db.execute(
    select(Alert).where(
        Alert.dedup_key == dedup_key,
        Alert.created_at >= window_start
    )
)
if existing.scalar_one_or_none():
    return existing_alert  # Return existing instead of creating duplicate
```

### 1.3 Event-to-Alert Traceability
**Add correlation_id to Alert model:**
```python
correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
```

**In alert creation:**
```python
correlation_id = str(uuid.uuid4())  # Or hash of telemetry batch
```

---

## Phase 2: High - Rule Execution Audit & Timestamps (Week 2)

### 2.1 Rule Execution Audit Trail
**File:** `backend/src/sentinelwatch_backend/models/rule_execution.py` (new)

```python
class RuleExecution(Base):
    __tablename__ = "rule_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[str] = mapped_column(String(64), index=True)
    telemetry_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    triggered: Mapped[bool]
    evaluation_time_ms: Mapped[int]
    error: Mapped[Optional[str]]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
```

**In DetectionEngine.evaluate():**
```python
async def evaluate(self, telemetry, rule_id=None):
    start = time.perf_counter()
    # ... evaluation logic ...
    duration_ms = int((time.perf_counter() - start) * 1000)

    # Log execution
    execution = RuleExecution(
        rule_id=rule.rule_id,
        telemetry_id=telemetry.get("id"),
        triggered=triggered,
        evaluation_time_ms=duration_ms,
        error=str(e) if error else None
    )
    db.add(execution)
```

### 2.2 Detection Timestamps
**Add to DetectionResult:**
```python
evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
triggered_at: Optional[datetime] = None  # When rule actually triggered
```

---

## Phase 3: Medium - Risk Scoring & Rule Versioning (Week 3)

### 3.1 Enhanced Risk Scoring
**File:** `rule_model.py` - enhance `_calculate_risk_score`

```python
def _calculate_risk_score(self, rule, telemetry):
    # Multi-factor scoring
    base = severity_scores.get(rule.severity, 50)

    # Evidence factors
    evidence_score = telemetry.get("evidence_strength", 0.5)

    # Asset criticality (from agent tags)
    asset_criticality = telemetry.get("asset_criticality", 1.0)

    # Threat intel score
    threat_intel = telemetry.get("threat_intel_score", 0.0)

    # Time decay (newer = higher)
    time_factor = 1.0
    if "create_time" in telemetry:
        age_hours = (datetime.now(timezone.utc) - telemetry["create_time"]).total_seconds() / 3600
        time_factor = max(0.1, 1.0 - (age_hours / 168))  # Decay over week

    return min(100, base * evidence_score * asset_criticality * (1 + threat_intel) * time_factor)
```

### 3.2 Rule Versioning in Engine
```python
class DetectionEngine:
    def __init__(self, rules=None):
        self.rule_versions = {}  # rule_id -> version
        self.rule_effective_dates = {}  # rule_id -> effective_date

    def add_rule(self, rule):
        self.rule_versions[rule.rule_id] = rule.version
        # Only evaluate if rule is effective
        if rule.promoted_from_staging_at and rule.promoted_from_staging_at > datetime.now(timezone.utc):
            return  # Not yet effective
```

---

## Phase 4: Low - Detection Latency & Failure Handling (Week 4)

### 4.1 Detection Latency Metrics
```python
class DetectionMetrics:
    collection_to_detection_ms: int
    detection_to_alert_ms: int
    total_latency_ms: int

    def record(self, collection_time, detection_time, alert_time):
        self.collection_to_detection_ms = int((detection_time - collection_time).total_seconds() * 1000)
        self.detection_to_alert_ms = int((alert_time - detection_time).total_seconds() * 1000)
```

### 4.2 Detection Failure Handling
```python
class DetectionEngine:
    def __init__(self):
        self.dead_letter_queue = asyncio.Queue()
        self.failure_metrics = Counter()

    async def evaluate_with_fallback(self, telemetry, rule_id=None):
        try:
            return await self.evaluate(telemetry, rule_id)
        except Exception as e:
            await self.dead_letter_queue.put({
                "telemetry": telemetry,
                "rule_id": rule_id,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc)
            })
            self.failure_metrics.increment("evaluation_errors")
            return []
```

---

## Implementation Priority Order

| Week | Task | File(s) | Effort |
|------|------|---------|--------|
| 1 | Stable Alert IDs | `agent_communication.py`, `models/alert.py` | Medium |
| 1 | Alert Deduplication | `models/alert.py`, `agent_communication.py` | Medium |
| 1 | Correlation IDs | `models/alert.py`, `agent_communication.py` | Medium |
| 2 | Rule Execution Audit | `models/rule_execution.py`, `rule_model.py` | Medium |
| 2 | Detection Timestamps | `rule_model.py`, `models/alert.py` | Low |
| 3 | Enhanced Risk Scoring | `rule_model.py` | Medium |
| 3 | Rule Versioning in Engine | `rule_model.py` | Medium |
| 4 | Detection Latency Metrics | `agent_communication.py` | Low |
| 4 | Failure Handling | `rule_model.py` | Low |

---

## Test Requirements

For each change, add tests:

```python
# tests/test_detection_stable_ids.py
def test_stable_alert_id_deterministic():
    id1 = generate_stable_alert_id("PR-002", "agent-123", datetime(2025, 1, 1, 10, 0, 0))
    id2 = generate_stable_alert_id("PR-002", "agent-123", datetime(2025, 1, 1, 10, 0, 0))
    assert id1 == id2

# tests/test_detection_deduplication.py
def test_alert_deduplication_same_window():
    alert1 = create_alert(rule_id="PR-002", agent_id="agent-1", window=datetime(2025,1,1,10,0))
    alert2 = create_alert(rule_id="PR-002", agent_id="agent-1", window=datetime(2025,1,1,10,0))
    assert alert1.id == alert2.id  # Same dedup key returns same alert

# tests/test_correlation_id.py
def test_correlation_id_propagated():
    correlation_id = "corr-123"
    alert = create_alert(correlation_id=correlation_id)
    assert alert.correlation_id == correlation_id
```

---

## Success Criteria

| Metric | Target |
|------|--------|
| Alert ID stability | Same rule+entity+window → same ID 100% |
| Deduplication rate | < 1% duplicate alerts in 1hr window |
| Correlation ID propagation | 100% telemetry→detection→alert |
| Rule execution audit coverage | 100% of evaluations logged |
| Detection timestamp accuracy | < 1ms resolution |
| Detection latency | < 100ms p99 |

---

## Rollout Plan

1. **Deploy Phase 1** (alert IDs, dedup, correlation) - backward compatible
2. **Deploy Phase 2** (audit, timestamps) - additive
3. **Deploy Phase 3** (risk scoring, versioning) - feature flags
4. **Deploy Phase 4** (metrics, failures) - monitoring only

Rollback plan: Feature flags for each phase, can disable independently.
