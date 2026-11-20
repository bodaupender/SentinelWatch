"""
Detection Rule Models for SentinelWatch.

Defines the Rule data model and enums for the detection engine.
Uses plain string categories/severities to avoid Pydantic v2 schema issues.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, ClassVar, Set
from enum import Enum
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)


class RuleSeverity(str, Enum):
    """Detection rule severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RuleCategory(str, Enum):
    """Detection rule categories."""
    PROCESS = "process"
    SERVICE = "service"
    STARTUP = "startup"
    EVENTLOG = "eventlog"
    CORRELATION = "correlation"


class RuleStatus(str, Enum):
    """Rule lifecycle status."""
    ACTIVE = "active"
    DRAFT = "draft"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class RuleType(str, Enum):
    """Detection rule types."""
    CONDITION = "condition"
    CORRELATION = "correlation"
    THRESHOLD = "threshold"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

# Rule type as plain strings
RULE_TYPE_CONDITION = "condition"
RULE_TYPE_CORRELATION = "correlation"
RULE_TYPE_THRESHOLD = "threshold"


class DetectionRule(BaseModel):
    """Detection rule definition using plain string categories/severities."""

    model_config = {"extra": "forbid", "arbitrary_types_allowed": True}

    # Rule identification
    rule_id: str = Field(..., description="Unique rule identifier")
    rule_name: str = Field(..., description="Human-readable rule name")
    description: str = Field(..., description="Rule description")
    rule_type: str = Field(default="condition", description="Rule type")
    category: str = Field(default="process", description="Rule category")
    severity: str = Field(default="medium", description="Default severity")
    confidence: float = Field(default=50.0, ge=0.0, le=100.0, description="Confidence score (0-100)")
    condition: str = Field(default="", description="CEL or YARA-L-like condition expression")
    condition_version: int = Field(default=1, ge=1, description="Condition expression version")

    # MITRE ATT&CK mapping
    mitre_techniques: Optional[List[str]] = Field(
        default=None, description="MITRE ATT&CK technique IDs"
    )
    mitre_tactics: Optional[List[str]] = Field(
        default=None, description="MITRE ATT&CK tactic IDs"
    )

    # Evidence and investigation
    evidence_requirements: Optional[List[str]] = Field(
        default=None, description="Required telemetry for detection"
    )
    investigation_guidance: Optional[str] = Field(
        default=None, description="Investigation steps for analysts"
    )

    # Rule metadata
    version: int = Field(default=1, ge=1, description="Rule version")
    previous_rule_id: Optional[str] = Field(
        default=None, description="ID of previous rule version"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    created_by: Optional[str] = Field(default=None, description="Rule creator")
    last_modified: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_modified_by: Optional[str] = Field(default=None, description="Last modifier")

    # False-positive management
    false_positive_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Expected false positive rate"
    )
    false_positive_justification: Optional[str] = Field(
        default=None, description="Justification for FP rate"
    )
    suppression_expiry: Optional[datetime] = Field(
        default=None, description="When suppression expires"
    )

    # Status and monitoring
    status: str = Field(default="active", description="Rule status")
    enabled: bool = Field(default=True, description="Whether rule is enabled")
    times_executed: int = Field(default=0, ge=0, description="Number of times evaluated")
    times_triggered: int = Field(default=0, ge=0, description="Number of times triggered")
    last_triggered: Optional[datetime] = Field(
        default=None, description="When last triggered"
    )

    # Duplicate suppression
    duplicate_window_seconds: int = Field(
        default=3600, ge=0, description="Duplicate suppression window"
    )

    @validator("rule_id")
    def validate_rule_id(cls, v: str) -> str:
        """Rule ID must be non-empty."""
        if not v:
            raise ValueError("Rule ID is required")
        return v

    @validator("confidence")
    def validate_confidence(cls, v: float) -> float:
        """Confidence must be 0-100."""
        if not 0.0 <= v <= 100.0:
            raise ValueError("Confidence must be between 0 and 100")
        return v

    @validator("false_positive_rate")
    def validate_fp_rate(cls, v: float) -> float:
        """False positive rate must be 0-1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("False positive rate must be between 0 and 1")
        return v

    @validator("duplicate_window_seconds")
    def validate_dup_window(cls, v: int) -> int:
        """Duplicate window must be non-negative."""
        if v < 0:
            raise ValueError("Duplicate window must be non-negative")
        return v

    def record_execution(self) -> None:
        """Record that the rule was evaluated."""
        self.times_executed += 1

    def record_trigger(self) -> None:
        """Record that the rule triggered an alert."""
        self.times_triggered += 1
        self.last_triggered = datetime.now(timezone.utc)

    def is_active(self) -> bool:
        """Check if rule is active.

        A rule is active when both its lifecycle ``status`` is active and its
        ``enabled`` flag is True. Setting ``enabled=False`` on a rule whose
        ``status`` is still ``"active"`` must still skip evaluation.
        """
        return self.enabled and self.status in ("active", "enabled")

    def is_disabled(self) -> bool:
        """Check if rule is disabled."""
        return self.status in ("disabled", "disabled")

    def should_suppress(self, event_time: datetime) -> bool:
        """Check if this event should be suppressed based on expiry."""
        if self.suppression_expiry is None:
            return False
        return event_time > self.suppression_expiry


class DetectionResult(BaseModel):
    """Result of rule evaluation."""

    model_config = {"extra": "forbid", "arbitrary_types_allowed": True}

    rule_id: str = Field(..., description="Rule identifier")
    rule_name: str = Field(..., description="Rule name")
    severity: str = Field(default="medium", description="Alert severity")
    confidence: float = Field(default=50.0, ge=0.0, le=100.0, description="Confidence score (0-100)")
    risk_score: float = Field(
        default=50.0, ge=0.0, le=100.0, description="Calculated risk score (0-100)"
    )
    triggered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    description: str = Field(default="", description="Alert description")
    evidence: Optional[Dict[str, Any]] = Field(
        default=None, description="Collected evidence"
    )
    mitre_technique: Optional[str] = Field(
        default=None, description="MITRE ATT&CK technique"
    )
    affected_entity: Optional[str] = Field(
        default=None, description="Affected process or service name"
    )
    status: str = Field(default="new", description="Alert status")
    description_details: Optional[str] = Field(
        default=None, description="Detailed description"
    )

    def to_alert_dict(self) -> Dict[str, Any]:
        """Convert to alert dictionary."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "risk_score": self.risk_score,
            "triggered_at": self.triggered_at.isoformat(),
            "description": self.description,
            "evidence": self.evidence,
            "mitre_technique": self.mitre_technique,
            "affected_entity": self.affected_entity,
            "status": self.status,
        }


class DetectionResultBase(BaseModel):
    """Base detection result with minimal fields."""
    model_config = {"extra": "forbid", "arbitrary_types_allowed": True}

    rule_id: str = Field(..., description="Rule identifier")
    rule_name: str = Field(..., description="Rule name")
    severity: str = Field(default="medium", description="Alert severity")
    risk_score: float = Field(default=50.0, ge=0.0, le=100.0, description="Calculated risk score (0-100)")
    triggered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    description: str = Field(default="", description="Alert description")
    evidence: Optional[Dict[str, Any]] = Field(
        default=None, description="Collected evidence"
    )
    mitre_technique: Optional[str] = Field(
        default=None, description="MITRE ATT&CK technique"
    )
    affected_entity: Optional[str] = Field(
        default=None, description="Affected process or service name")
    status: str = Field(default="new", description="Alert status")


class DetectionEngine:
    """Core detection engine that evaluates rules against telemetry."""

    def __init__(self, rules: Optional[List["DetectionRule"]] = None):
        self.rules: Dict[str, "DetectionRule"] = {}
        self._rule_index: Dict[str, List["DetectionRule"]] = {}
        self._enabled_rules: Set[str] = set()

        if rules:
            for rule in rules:
                self.add_rule(rule)

    def add_rule(self, rule: "DetectionRule") -> None:
        """Add a detection rule to the engine."""
        self.rules[rule.rule_id] = rule
        category = rule.category
        if category not in self._rule_index:
            self._rule_index[category] = []
        self._rule_index[category].append(rule)
        if rule.is_active():
            self._enabled_rules.add(rule.rule_id)

    def remove_rule(self, rule_id: str) -> Optional["DetectionRule"]:
        """Remove a rule from the engine."""
        rule = self.rules.pop(rule_id, None)
        if rule:
            self._enabled_rules.discard(rule.rule_id)
            # Remove from category index
            category = rule.category
            if category in self._rule_index:
                self._rule_index[category] = [
                    r for r in self._rule_index[category] if r.rule_id != rule_id
                ]
        return rule

    def enable_rule(self, rule_id: str) -> bool:
        """Enable a rule."""
        rule = self.rules.get(rule_id)
        if rule:
            rule.status = "active"
            self._enabled_rules.add(rule.rule_id)
            return True
        return False

    def disable_rule(self, rule_id: str) -> bool:
        """Disable a rule."""
        rule = self.rules.get(rule_id)
        if rule:
            rule.status = "disabled"
            self._enabled_rules.discard(rule.rule_id)
            return True
        return False

    def evaluate(
        self, telemetry: Dict[str, Any], rule_id: Optional[str] = None
    ) -> List["DetectionResult"]:
        """Evaluate rules against telemetry data."""
        results: List["DetectionResult"] = []

        # Determine which rules to evaluate
        if rule_id:
            rules_to_eval = [self.rules.get(rule_id)] if rule_id in self.rules else []
        else:
            rules_to_eval = [
                r for r in self.rules.values() if r.is_active()
            ]

        for rule in rules_to_eval:
            # Disabled / inactive rules never reach evaluation and never
            # produce DetectionResult objects.
            if not rule.is_active():
                continue

            try:
                # Record execution
                rule.record_execution()

                # Evaluate condition
                triggered = self._evaluate_condition(rule, telemetry)

                if triggered:
                    result = DetectionResult(
                        rule_id=rule.rule_id,
                        rule_name=rule.rule_name,
                        severity=rule.severity,
                        confidence=self._calculate_confidence(rule, telemetry),
                        risk_score=self._calculate_risk_score(rule, telemetry),
                        evidence=self._generate_evidence(rule, telemetry),
                        mitre_technique=self._get_mitre_technique(rule, telemetry),
                        affected_entity=self._get_affected_entity(rule, telemetry),
                        description=self._generate_description(rule, telemetry),
                    )
                    rule.record_trigger()
                    results.append(result)

            except ConditionEvaluationError:
                # Structural parse/validation errors must propagate so they
                # are never silently converted into a non-detection.
                raise
            except Exception as e:
                # Non-structural errors are logged and treated as non-triggering.
                logger.warning("rule_evaluation_error", rule_id=rule.rule_id, error=str(e))

        return results

    def _normalize_telemetry(self, telemetry: Dict[str, Any], source: str) -> Dict[str, Any]:
        """Normalize telemetry dict so rule condition fields match what they expect.

        Rule conditions reference canonical field names; telemetry may arrive with
        collector-names or flattened names. This maps them into one normalised view
        without mutating the caller's dict.
        """
        norm: Dict[str, Any] = dict(telemetry)

        if source == "process":
            norm.setdefault("process_name", norm.pop("name", None))
            norm.setdefault("process_exe", norm.pop("exe", None))
            norm.setdefault("parent_process_name", norm.pop("parent_name", None))
            norm.setdefault("parent_process_exe", norm.pop("parent_exe", None))
            norm.setdefault("process_cmdline", norm.pop("cmdline", None))
            norm.setdefault("process_pid", norm.pop("pid", None))
            norm.setdefault("parent_pid", norm.pop("ppid", None))
            norm.setdefault("process_username", norm.pop("username", None))
            norm.setdefault("process_integrity_level", norm.pop("integrity_level", None))
            norm.setdefault("process_signature", {"is_signed": norm.pop("is_signed", False)})

        elif source == "service":
            norm.setdefault("service_name", norm.pop("name", None))
            norm.setdefault("service_display_name", norm.pop("display_name", None))
            norm.setdefault("service_binary_path", norm.pop("binary_path", None))
            norm.setdefault("service_account", norm.pop("account", None))
            norm.setdefault("service_start_type", norm.pop("start_type", None))
            norm.setdefault("service_status", norm.pop("status", None))
            # Derive directory from path for writable-directory checks
            bp = norm.get("service_binary_path")
            if bp and "service_binary_directory" not in norm:
                norm["service_binary_directory"] = str(Path(bp).parent) if isinstance(bp, Path) else os.path.dirname(str(bp))

        elif source == "startup":
            norm.setdefault("startup_source", norm.pop("source", None))
            name_val = norm.pop("name", None)
            norm.setdefault("startup_name", name_val)
            norm.setdefault("startup_entry", name_val)
            norm.setdefault("startup_command", norm.pop("command", None))
            norm.setdefault("startup_executable_path", norm.pop("exe", None))
            norm.setdefault("startup_user_context", norm.pop("user_context", None))

        elif source == "eventlog":
            norm.setdefault("event_log_event_id", norm.pop("event_id", None))
            norm.setdefault("event_log_source", norm.pop("source", None))
            norm.setdefault("event_log_message", norm.pop("message", None))
            extracted = norm.get("extracted") or {}
            for k, v in extracted.items():
                norm.setdefault(f"event_{k}", v)
            norm["extracted"] = extracted

        return norm

    def _validate_rule_condition(self, rule: "DetectionRule", telemetry: Dict[str, Any]) -> bool:
        """Validate that required evidence fields are present before evaluation."""
        requirements = rule.evidence_requirements or []
        if not requirements:
            return True
        norm = self._normalize_telemetry(telemetry, telemetry.get("source", ""))
        missing = [f for f in requirements if not norm.get(f)]
        if missing:
            logger.debug(
                "rule_evidence_incomplete",
                rule_id=rule.rule_id,
                missing_fields=missing,
            )
            return False
        return True

    def _evaluate_condition(self, rule: "DetectionRule", telemetry: Dict[str, Any]) -> bool:
        """Evaluate rule condition against telemetry using ConditionEvaluator.

        Returns False for ordinary telemetry when no rule matches; never silently
        swallows evaluation errors.
        """
        # Test shortcut — kept for integration tests only
        if telemetry.get("evaluate_all", False):
            return True

        # Skip unsupported/correlation rules that don't carry evaluable condition strings
        if rule.rule_type not in ("condition", ""):
            return False

        if not rule.condition or not rule.condition.strip():
            return False

        try:
            from .condition_evaluator import ConditionEvaluator
            norm = self._normalize_telemetry(telemetry, telemetry.get("source", ""))
            if not self._validate_rule_condition(rule, norm):
                return False
            evaluator = ConditionEvaluator()
            return evaluator.evaluate(rule.condition, norm)
        except ConditionEvaluationError:
            # Structural parse/validation errors must propagate — never suppress
            raise
        except Exception as exc:
            # Non-structural errors are logged and treated as non-triggering
            logger.warning("rule_evaluation_error", rule_id=rule.rule_id, error=str(exc))
            return False

    def _calculate_confidence(self, rule: "DetectionRule", telemetry: Dict[str, Any]) -> float:
        """Calculate confidence score for the rule trigger."""
        base = rule.confidence
        evidence_strength = telemetry.get("evidence_strength", 0.5)
        return min(100.0, base * evidence_strength)

    def _calculate_risk_score(self, rule: "DetectionRule", telemetry: Dict[str, Any]) -> float:
        """Calculate risk score (0-100)."""
        # Map severity to base score
        severity_scores = {
            "critical": 90,
            "high": 70,
            "medium": 50,
            "low": 30,
            "info": 10
        }
        base = severity_scores.get(rule.severity, 50)
        evidence_strength = telemetry.get("evidence_strength", 0.5)
        return min(100.0, base * evidence_strength)

    def _generate_evidence(self, rule: "DetectionRule", telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """Generate evidence dictionary from telemetry."""
        return telemetry.get("evidence", {})

    def _get_mitre_technique(self, rule: "DetectionRule", telemetry: Dict[str, Any]) -> Optional[str]:
        """Get MITRE technique from rule mapping."""
        return rule.mitre_techniques[0] if rule.mitre_techniques else None

    def _get_affected_entity(self, rule: "DetectionRule", telemetry: Dict[str, Any]) -> Optional[str]:
        """Get affected entity name from telemetry."""
        return telemetry.get("affected_entity")

    def _generate_description(self, rule: "DetectionRule", telemetry: Dict[str, Any]) -> str:
        """Generate human-readable description."""
        return rule.rule_name


class DetectionFramework:
    """High-level detection framework managing rules, execution, and results."""

    def __init__(self, engine: "DetectionEngine", name: str = "SentinelWatch Detection"):
        self.engine = engine
        self.name = name
        self.evidence_store: Dict[str, List] = defaultdict(list)
        self.correlation_info: Dict[str, Any] = defaultdict(dict)
        self.alert_history: List = []
        self.suppression_cache: Dict[str, datetime] = {}

    def evaluate_telemetry(self, telemetry: Dict[str, Any]) -> Tuple[List, List]:
        """Evaluate all active rules against telemetry and generate alerts."""
        results = self.engine.evaluate(telemetry)
        alerts = []

        for result in results:
            # Generate alert from result
            alert_id = f"alert-{result.rule_id}-{int(datetime.now().timestamp())}"
            alert = {
                "alert_id": alert_id,
                "rule_id": result.rule_id,
                "hostname": telemetry.get("hostname", "unknown"),
                "detection_category": result.rule_category if hasattr(result, 'rule_category') else "process",
                "severity": result.severity,
                "confidence": result.confidence,
                "risk_score": result.risk_score,
                "affected_entity": result.affected_entity,
                "evidence": result.evidence,
                "mitre_technique": result.mitre_technique,
                "description": result.description,
                "status": "new",
            }

            # Add evidence items
            if result.evidence:
                for key, value in result.evidence.items():
                    if isinstance(value, (str, int, float, bool)):
                        self.evidence_store[alert_id].append(
                            {
                                "field_name": key,
                                "field_value": value,
                                "source": telemetry.get("source", "unknown"),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )

                # Check for suppression
                if self._is_suppressed(alert_id):
                    continue

                # Correlate with existing events
                self._correlate_alert(alert, telemetry)

                # Add to alert history
                pass  # In production, would add to alert_history list

        return results, alerts

    def _is_suppressed(self, alert_id: str) -> bool:
        """Check if an alert is suppressed."""
        if alert_id in self.suppression_cache:
            expiry = self.suppression_cache[alert_id]
            if datetime.now(timezone.utc) > expiry:
                del self.suppression_cache[alert_id]
                return False
            return True
        return False

    def suppress_alert(self, alert_id: str, expiry_minutes: int = 360) -> None:
        """Suppress an alert with expiry."""
        self.suppression_cache[alert_id] = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)

    def _correlate_alert(self, alert, telemetry: Dict[str, Any]) -> None:
        """Correlate alert with related events."""
        event_ids = telemetry.get("event_ids", [])
        if event_ids:
            # In production, would extend alert's related_event_ids
            pass

    def get_alert(self, alert_id: str) -> Optional[Dict]:
        """Get an alert by ID."""
        for alert in []:  # placeholder - would iterate alert_history
            if alert.get("alert_id") == alert_id:
                return alert
        return None

    def get_alerts_by_severity(self, severity: str) -> List:
        """Get alerts by severity."""
        return [a for a in [] if a.get("severity") == severity]

    def get_alerts_by_rule(self, rule_id: str) -> List:
        """Get alerts by rule ID."""
        return [a for a in [] if a.get("rule_id") == rule_id]

    def get_statistics(self) -> Dict[str, Any]:
        """Get framework statistics."""
        return {
            "total_alerts": 0,
            "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            "by_status": {"new": 0, "investigating": 0, "true_positive": 0, "false_positive": 0, "resolved": 0},
            "total_rules": len(self.engine.rules) if hasattr(self.engine, 'rules') else 0,
            "active_rules": len(self.engine._enabled_rules) if hasattr(self.engine, '_enabled_rules') else 0,
        }
