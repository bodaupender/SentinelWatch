# SentinelWatch Detection Engine Audit

**Date**: 2025-11-15
**Auditor**: Claude (Phase 5 Task 1)
**Scope**: Complete audit of detection engine, rules, and alert generation

---

## Executive Summary

The detection engine has a solid foundation but lacks production-grade reliability features. Key findings:

| Area | Status | Severity |
|------|--------|----------|
| Rule-based detection | ✅ Implemented | - |
| Condition evaluation | ✅ Fixed (list parsing fixed) | - |
| Evidence-backed alerts | ⚠️ Partial | Medium |
| Stable alert identifiers | ❌ Missing | Critical |
| Alert deduplication | ⚠️ Basic only | High |
| Severity classification | ✅ Implemented | - |
| Risk scoring | ⚠️ Basic | Medium |
| Rule versioning | ⚠️ Model only | Medium |
| Rule execution audit | ⚠️ Print only | Medium |
| Detection timestamps | ⚠️ Partial | Medium |
| Event-to-alert traceability | ❌ Missing | Critical |
| Alert deduplication | ❌ Missing | Critical |
| Stable alert identifiers | ❌ Missing | Critical |
| Rule versioning | ⚠️ Model only | Medium |
| Rule execution audit | ⚠️ Print only | Medium |
| Detection timestamps | ⚠️ Partial | Medium |
| Event-to-alert traceability | ❌ Missing | Critical |

---

## 1. Existing Detection Rules (23 rules)

### Process Rules (10)
| Rule ID | Name | Severity | MITRE | Condition |
|---------|------|----------|-------|-----------|
| PR-001 | Lookalike Process Name | medium | T1036.005 | name in lookalike list & exe not in expected paths |
| PR-002 | Office Spawning Script | high | T1059.001, T1059.005 | parent in Office apps & child in script interpreters |
| PR-003 | Unexpected Script Interpreter | medium | T1059.001, T1059.003, T1059.005 | script interpreter exe not in System32/SysWOW64 |
| PR-004 | Executable in Unusual Directory | medium | T1059, T1204 | exe in temp/appdata/downloads |
| PR-005 | Suspicious Temp Execution | high | T1059, T1204 | exe in temp/tmp & not installer |
| PR-006 | Unsigned Executable Anomaly | medium | T1055, T1036 | unsigned & running as SYSTEM/High integrity |
| PR-007 | Unexpected Privileged Process | high | T1055, T1068 | High/System integrity & not in expected list |
| PR-008 | Suspicious Command Line | high | T1059.001, T1027, T1218 | regex for encoded/obfuscated commands |
| PR-009 | Process Baseline Deviation | medium | T1059, T1053 | execution time/user/frequency deviation |
| PR-010 | Unexpected Process Execution | medium | T1059 | process not in baseline/allowed |

### Service Rules (5)
| Rule ID | Name | Severity | MITRE | Condition |
|---------|------|----------|-------|-----------|
| SV-001 | Unquoted Service Path | high | T1543.003 | unquoted path with spaces |
| SV-002 | Writable Service Binary | medium | T1543.003 | binary writable by non-admin |
| SV-003 | Writable Service Directory | medium | T1543.003 | directory writable by non-admin |
| SV-004 | Unexpected Service Install | high | T1543.003 | new service not in known list |
| SV-005 | Suspicious Service Account | high | T1543.003 | account not LocalSystem/NetworkService/LocalService |

### Startup Rules (6)
| Rule ID | Name | Severity | MITRE | Condition |
|---------|------|----------|-------|-----------|
| ST-001 | Unexpected Startup Entry | high | T1547.001, T1053.005 | new entry in registry/tasks/folder |
| ST-002 | New Startup Entry | medium | T1547.001, T1053.005 | new since last collection |
| ST-003 | Startup Path Anomaly | medium | T1547.001, T1053.005 | path in temp/appdata/downloads |
| ST-004 | Startup Baseline Deviation | medium | T1547, T1053 | count > 1.5x baseline |
| ST-005 | Suspicious Scheduled Task | high | T1053.005 | script interpreter with persistence trigger |
| ST-006 | Unusual Auto-Start Service | medium | T1543.003 | auto-start service not in baseline |

### Correlation Rules (2)
| Rule ID | Name | Severity | MITRE | Condition |
|---------|------|----------|-------|-----------|
| CR-001 | Process-Service Correlation | high | T1543.003, T1055 | service install + process creation within 300s |
| CR-002 | Logon-Process Correlation | medium | T1059, T1556 | logon 4624 + suspicious process within 600s |

---

## 2. Rule Execution Flow

```
Telemetry Ingestion → DetectionEngine.evaluate()
    → Filter active rules (or specific rule_id)
    → For each rule:
        → record_execution()
        → _evaluate_condition(rule, telemetry)
            → ConditionEvaluator.evaluate(rule.condition, telemetry)
            → Tokenize → Parse → Evaluate AST
        → If triggered:
            → record_trigger()
            → Create DetectionResult with:
                - rule_id, rule_name, severity
                - confidence = rule.confidence * evidence_strength
                - risk_score = severity_base * evidence_strength
                - evidence = telemetry.get("evidence", {})
                - mitre_technique = rule.mitre_techniques[0]
                - affected_entity = telemetry.get("affected_entity")
                - description = rule.rule_name
            → rule.record_trigger()
    → Return list of DetectionResult
```

---

## 3. Event Normalization

**Current State:**
- Telemetry comes in as dict with varying structures
- Source field added by ingestion pipeline
- Parent process fields mapped from `parent_name`/`parent_process_name`
- Timestamps converted to UTC
- No schema validation or normalization layer
- Raw telemetry passed directly to condition evaluator

**Issues:**
- No canonical event schema
- Field names inconsistent (parent_name vs parent_process_name)
- No validation of required fields per source type
- No enrichment (geo, reputation, etc.)

---

## 4. Detection Conditions

**Condition Language:**
- Supports: `in`, `not in`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `and`, `or`, `not`, `matches regex`
- List literals: `["a", "b", "c"]`
- Field access: `field_name` or nested `field.subfield`
- Regex: `field matches regex "pattern"`

**Issues:**
- No validation of condition syntax at rule creation
- No dry-run/test capability
- Case sensitivity inconsistent (IGNORECASE on regex but not on `in`)
- List parsing was broken (now fixed)
- No condition validation at rule load time

---

## 5. Alert Creation

**Current Flow:**
```
DetectionResult → Alert (in agent_communication.py submit_telemetry)
    → Create Evidence record
    → Create Alert with:
        - rule_id, rule_name, severity
        - status="new"
        - mitre_techniques, mitre_tactics
        - finding_count=1
        - summary=result.description
        - evidence_id linking to Evidence
```

**Issues:**
- Alert ID generated as `alert-{rule_id}-{timestamp}` - not stable
- No deduplication key (rule + entity + time window)
- Evidence stored as raw JSON, not structured
- No correlation ID linking related alerts
- No alert correlation logic implemented

---

## 6. Severity Assignment

**Current:** Direct mapping from rule.severity
- CRITICAL, HIGH, MEDIUM, LOW, INFO
- No dynamic adjustment based on context
- No asset criticality weighting
- No threat intelligence enrichment

---

## 6. Risk Scoring

**Current Formula:**
```
risk_score = severity_base * evidence_strength
severity_base: critical=90, high=70, medium=50, low=30, info=10
evidence_strength: telemetry.get("evidence_strength", 0.5)
```

**Issues:**
- Fixed evidence_strength default (0.5) - not calculated
- No asset value consideration
- No threat intelligence scoring
- No environmental context (time, user, asset criticality)
- Linear scaling only

---

## 7. Duplicate Alert Prevention

**Current:** Only suppression cache in DetectionFramework
```python
suppression_cache: Dict[str, datetime]  # alert_id -> expiry
```
- Keyed by alert_id (which is timestamp-based)
- No deduplication by rule+entity+time_window
- No cross-agent deduplication
- Suppression only in framework, not in engine

---

## 8. Detection Latency

**Current:**
- Collection interval: 30s (process), 60s (service), 10s (eventlog)
- Detection runs inline with ingestion
- No async/background processing
- No latency metrics collected

---

## 9. Detection Failures

**Current:**
- Exceptions caught and silently ignored (pass)
- Print statements for debugging
- No metrics on evaluation failures
- No dead letter queue for failed evaluations
- No alerting on detection failures

---

## Critical Gaps Summary

| Gap | Impact | Effort |
|-----|--------|--------|
| Stable alert IDs (rule+entity+timewindow hash) | Critical - cannot track alerts | Medium |
| Alert deduplication (rule+entity+timewindow) | Critical - alert storms | Medium |
| Event-to-alert traceability (correlation IDs) | Critical - investigation broken | Medium |
| Rule execution audit trail | High - compliance | Low |
| Stable alert IDs | Critical | Medium |
| Alert deduplication | Critical | Medium |
| Event-to-alert traceability | Critical | Medium |
| Rule execution audit | High | Low |
| Detection timestamps | Medium | Low |
| Risk scoring enhancement | Medium | Medium |

---

## Recommended Remediation Priority

### Phase 1: Critical (Week 1)
1. **Stable Alert IDs** - Hash(rule_id + entity_id + time_window)
2. **Alert Deduplication** - Rule+Entity+TimeWindow key with configurable window
2. **Event-to-Alert Traceability** - Correlation IDs linking telemetry→detection→alert
2. **Stable Alert IDs** - Deterministic IDs for tracking

### Phase 2: High (Week 2)
3. **Alert Deduplication** - Rule+Entity+TimeWindow with configurable window
3. **Event-to-Alert Traceability** - Correlation IDs end-to-end
3. **Rule Execution Audit** - Structured logging to audit table
4. **Detection Timestamps** - Created/evaluated/triggered timestamps

### Phase 3: Medium (Week 3)
5. **Risk Scoring Enhancement** - Multi-factor scoring
5. **Rule Versioning** - Engine-level version tracking
5. **Detection Latency Metrics** - Collection→Detection→Alert timing
5. **Detection Failure Handling** - Dead letter queue, metrics

### Phase 4: Low (Week 4)
6. **Rule Versioning in Engine** - Version-aware evaluation
6. **Detection Latency Optimization** - Async processing
6. **Cross-Agent Deduplication** - Global deduplication

---

## Test Plan

For each rule, test:
- **Positive cases** - Known malicious samples that should trigger
- **Negative cases** - Benign activity that should not trigger
- **Edge cases** - Boundary conditions, missing fields, malformed data
- **Performance** - Evaluation time < 1ms per rule
- **Deduplication** - Same event doesn't create duplicate alerts
- **Traceability** - Event → Detection → Alert traceable

---

## Next Steps

1. Implement stable alert IDs (hash of rule_id + entity + time_window)
2. Implement alert deduplication with configurable time window
3. Add correlation IDs for event-to-alert traceability
3. Add structured audit logging for rule execution
4. Enhance risk scoring with multi-factor model
4. Add rule versioning to engine
4. Add detection latency metrics
4. Implement detection failure handling
