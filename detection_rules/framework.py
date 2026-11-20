"""
SentinelWatch Detection Framework.

Provides the core framework for rule evaluation, evidence management,
and alert generation. This is the reusable engine that processes
telemetry and produces structured detection results.
"""

import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from .rule_model import (
    DetectionRule,
    DetectionResult,
    DetectionEngine,
    RuleCategory,
    RuleSeverity,
    RuleStatus,
    AlertSeverity,
)


class EvidenceItem(BaseModel):
    """A piece of evidence collected during detection."""

    model_config = {"extra": "forbid"}

    field_name: str = Field(..., description="Name of the evidence field")
    field_value: Any = Field(..., description="Value of the evidence field")
    source: str = Field(..., description="Source of the evidence (e.g., 'process', 'service', 'eventlog')")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class AlertBase(BaseModel):
    """Base alert model with common fields."""

    model_config = {"extra": "forbid"}

    alert_id: str = Field(..., description="Unique alert identifier")
    rule_id: str = Field(..., description="Rule that generated the alert")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    hostname: str = Field(..., description="Affected host")
    detection_category: str = Field(
        default=RuleCategory.PROCESS.value, description="Detection category")
    severity: AlertSeverity = Field(
        default=AlertSeverity.MEDIUM, description="Alert severity")
    confidence: float = Field(
        default=50.0, ge=0.0, le=100.0, description="Confidence score")
    risk_score: float = Field(
        default=50.0, ge=0.0, le=100.0, description="Calculated risk score")
    affected_entity: Optional[str] = Field(
        default=None, description="Affected process or service name")
    evidence: Optional[Dict[str, Any]] = Field(
        default=None, description="Collected evidence")
    mitre_technique: Optional[str] = Field(
        default=None, description="MITRE ATT&CK technique")
    description: str = Field(default="", description="Alert description")
    investigation_guidance: Optional[str] = Field(
        default=None, description="Investigation steps")
    status: str = Field(default="new", description="Alert status")
    related_event_ids: List[str] = Field(
        default_factory=list, description="Related event IDs")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule_id,
            "timestamp": self.timestamp.isoformat(),
            "hostname": self.hostname,
            "detection_category": self.detection_category,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "risk_score": self.risk_score,
            "affected_entity": self.affected_entity,
            "evidence": self.evidence,
            "mitre_technique": self.mitre_technique,
            "description": self.description,
            "investigation_guidance": self.investigation_guidance,
            "status": self.status,
            "related_event_ids": self.related_event_ids,
        }


class CorrelationInfo(BaseModel):
    """Information about correlated events."""
    model_config = {"extra": "forbid"}

    event_ids: List[str] = Field(default_factory=list)
    time_window_minutes: float = Field(default=5.0)
    related_fields: Dict[str, Any] = Field(default_factory=dict)
    evidence_aggregated: bool = Field(default=False)


class DetectionFramework:
    """Extended detection framework with evidence and correlation."""

    def __init__(self, engine, name: str = "SentinelWatch Detection"):
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
            alert = AlertBase(
                alert_id=f"alert-{result.rule_id}-{int(datetime.now().timestamp())}",
                rule_id=result.rule_id,
                hostname=telemetry.get("hostname", "unknown"),
                detection_category=result.rule_category if hasattr(result, 'rule_category') else RuleCategory.PROCESS.value,
                severity=result.severity,
                confidence=result.confidence,
                risk_score=result.risk_score,
                affected_entity=result.affected_entity,
                evidence=result.evidence,
                mitre_technique=result.mitre_technique,
                description=result.description,
                status="new",
            )

            # Add evidence items
            if result.evidence:
                for key, value in result.evidence.items():
                    if isinstance(value, (str, int, float, bool)):
                        self.evidence_store[alert.alert_id].append(
                            {
                                "field_name": key,
                                "field_value": value,
                                "source": telemetry.get("source", "unknown"),
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )

                # Check for suppression
                if self._is_suppressed(alert.alert_id):
                    continue

                # Correlate with existing events
                self._correlate_alert(alert, telemetry)

                self.alert_history.append(alert)
                alerts.append(alert)

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
            alert.related_event_ids.extend(event_ids)

    def get_alert(self, alert_id: str) -> Optional[AlertBase]:
        """Get an alert by ID."""
        for alert in self.alert_history:
            if alert.alert_id == alert_id:
                return alert
        return None

    def get_alerts_by_severity(self, severity: AlertSeverity) -> List[AlertBase]:
        """Get alerts by severity."""
        return [a for a in self.alert_history if a.severity == severity]

    def get_alerts_by_rule(self, rule_id: str) -> List[AlertBase]:
        """Get alerts by rule ID."""
        return [a for a in self.alert_history if a.rule_id == rule_id]

    def get_statistics(self) -> Dict[str, Any]:
        """Get framework statistics."""
        total_alerts = len(self.alert_history)
        by_severity = {
            s.value: sum(1 for a in self.alert_history if a.severity == s)
            for s in AlertSeverity
        }
        by_status = {
            s: sum(1 for a in self.alert_history if a.status == s)
            for s in ["new", "investigating", "true_positive", "false_positive", "resolved"]
        }
        return {
            "total_alerts": len(self.alert_history),
            "by_severity": by_severity,
            "by_status": by_status,
            "total_rules": len(self.engine.rules),
            "active_rules": len(self.engine._enabled_rules),
        }


# Add timedelta import
from datetime import timedelta
