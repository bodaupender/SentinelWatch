"""Tests for DetectionEngine — wiring to ConditionEvaluator."""
from datetime import datetime, timezone

import pytest

from sentinelwatch_backend.detection_rules import ALL_RULES, DetectionEngine
from sentinelwatch_backend.detection_rules.rule_model import DetectionRule


# ---------- fixture helpers ----------

def _make_rule(rule_id, condition, category="process", evidence_requirements=None,
               rule_type="condition", enabled=True):
    return DetectionRule(
        rule_id=rule_id,
        rule_name=f"Test {rule_id}",
        description="test",
        category=category,
        severity="medium",
        confidence=50.0,
        condition=condition,
        evidence_requirements=evidence_requirements,
        rule_type=rule_type,
        enabled=enabled,
    )


def _make_engine(rules=None):
    return DetectionEngine(rules or [])


@pytest.fixture()
def engine():
    """Provide an empty DetectionEngine instance for tests that need one."""
    return DetectionEngine([])


# ---------- positive: real conditions now trigger ----------

class TestDetectionEnginePositive:
    def test_lookalike_process_detects_sandwich(self, engine):
        rule = _make_rule(
            "PR-LOOKALIKE",
            'process_name in ["sihost.exe", "svch0st.exe"] and process_exe not in expected_paths',
        )
        engine = _make_engine([rule])
        telemetry = {"process_name": "svch0st.exe", "process_exe": "C:\\Temp\\evil.exe"}
        results = engine.evaluate(telemetry)
        assert len(results) == 1
        assert results[0].rule_id == "PR-LOOKALIKE"

    def test_office_spawning_script(self, engine):
        rule = _make_rule(
            "PR-OFFICE-SCRIPT",
            'parent_process_name in ["WINWORD.EXE"] and process_name in ["powershell.exe", "cmd.exe"]',
        )
        engine = _make_engine([rule])
        telemetry = {
            "source": "process",
            "process_name": "cmd.exe",
            "parent_process_name": "WINWORD.EXE",
        }
        results = engine.evaluate(telemetry)
        assert len(results) == 1
        assert results[0].rule_id == "PR-OFFICE-SCRIPT"

    def test_unusual_executable_directory(self, engine):
        rule = _make_rule(
            "PR-UNUSUAL-DIR",
            'process_exe matches regex "(?i)(temp|tmp|appdata)"',
        )
        engine = _make_engine([rule])
        telemetry = {"process_exe": "C:\\Users\\me\\AppData\\Roaming\\tool.exe"}
        results = engine.evaluate(telemetry)
        assert len(results) == 1

    def test_correlation_rules_return_false(self, engine):
        """Correlation/threshold rules without evaluable condition strings."""
        rule = _make_rule(
            "CR-CORR",
            condition="",
            category="correlation",
            rule_type="correlation",
        )
        engine = _make_engine([rule])
        results = engine.evaluate({})
        assert len(results) == 0


# ---------- negative: ordinary telemetry does NOT trigger ----------

class TestDetectionEngineNegative:
    def test_empty_telemetry_no_trigger(self, engine):
        rule = _make_rule("X", 'process_name == "evil.exe"')
        assert len(_make_engine([rule]).evaluate({})) == 0

    def test_disabled_rule_not_evaluated(self, engine):
        rule = _make_rule("PR-DIS", 'process_name == "evil.exe"')
        rule.enabled = False
        engine = _make_engine([rule])
        results = engine.evaluate({"process_name": "evil.exe"})
        assert len(results) == 0


# ---------- entity-aware dedup prevention ----------

class TestEntityAwareDedup:
    """Two different processes triggering the same logical rule must not suppress one another."""

    def test_different_pids_same_rule_no_cross_suppress(self, engine):
        rule_a = _make_rule("PID-A", 'process_pid == 1001 and process_name == "evil.exe"')
        rule_b = _make_rule("PID-B", 'process_pid == 1002 and process_name == "evil.exe"')
        engine = _make_engine([rule_a, rule_b])
        t_a = {"process_name": "evil.exe", "process_pid": 1001}
        t_b = {"process_name": "evil.exe", "process_pid": 1002}
        r_a = engine.evaluate(t_a)
        r_b = engine.evaluate(t_b)
        # Both should fire independently (each rule has distinct pid in condition).
        ids = {res.rule_id for res in r_a + r_b}
        assert "PID-A" in ids
        assert "PID-B" in ids


# ---------- field normalisation ----------

class TestNormalisation:
    def test_process_fields_normalised(self, engine):
        rule = _make_rule("NRML", 'process_name == "evil.exe"')
        engine = _make_engine([rule])
        # Telemetry arrives with collector name "name"
        telemetry = {"name": "evil.exe"}
        # After normalisation, process_name should be set from name
        # This tests that the normaliser maps collector names -> canonical names
        norm = engine._normalize_telemetry(telemetry, "process")
        assert norm.get("process_name") == "evil.exe"

    def test_service_fields_normalised(self, engine):
        engine = _make_engine([])
        telemetry = {"name": "svcss", "binary_path": "C:\\Windows\\system32\\svc.dll"}
        norm = engine._normalize_telemetry(telemetry, "service")
        assert norm.get("service_name") == "svcss"
        assert norm.get("service_binary_path") == "C:\\Windows\\system32\\svc.dll"
        # Derive directory
        assert "service_binary_directory" in norm

    def test_startup_fields_normalised(self, engine):
        engine = _make_engine([])
        telemetry = {"source": "registry_run", "name": "MalwareStart"}
        norm = engine._normalize_telemetry(telemetry, "startup")
        assert norm.get("startup_source") == "registry_run"
        assert norm.get("startup_entry") == "MalwareStart"


# ---------- validation / evidence requirement ----------

class TestEvidenceValidation:
    def test_missing_required_field_skips_rule(self):
        rule = _make_rule(
            "EV",
            'process_name == "evil.exe"',
            evidence_requirements=["process_name", "process_exe"],
        )
        engine = _make_engine([rule])
        # Missing process_exe — rule should NOT trigger
        results = engine.evaluate({"process_name": "evil.exe"})
        assert len(results) == 0

    def test_all_required_fields_present(self):
        rule = _make_rule(
            "EV2",
            'process_name == "evil.exe"',
            evidence_requirements=["process_name", "process_exe"],
        )
        engine = _make_engine([rule])
        # Validate method returns True when all fields present
        assert engine._validate_rule_condition(rule, {"process_name": "evil.exe", "process_exe": "C:\\evil.exe"}) is True


# ---------- error propagation ----------

class TestErrorPropagation:
    def test_broken_condition_raises_not_silent(self, engine):
        """A parse error in a condition string must propagate as an exception,
        not return silently False."""
        bad_rule = _make_rule("BAD", "(process_name", enabled=True)
        engine = _make_engine([bad_rule])
        with pytest.raises(Exception):
            engine.evaluate({"process_name": "test"})

    def test_ok_conditions_still_work(self, engine):
        good_rule = _make_rule("GOOD", 'process_name == "test.exe"')
        engine = _make_engine([good_rule])
        results = engine.evaluate({"process_name": "test.exe"})
        assert len(results) == 1


# ---------- existing rule suite smoke test ----------

class TestAllRulesSmoke:
    """Verify ALL_RULES can be loaded and evaluated without crashing."""

    def test_all_rules_loadable(self):
        assert len(ALL_RULES) > 0

    def test_all_rules_in_engine(self):
        engine = DetectionEngine(ALL_RULES)
        assert len(engine.rules) == len(ALL_RULES)

    def test_normal_telemetry_no_crash(self):
        engine = DetectionEngine(ALL_RULES)
        # Completely empty telemetry: every rule evaluates to False
        engine.evaluate({})  # should not raise
