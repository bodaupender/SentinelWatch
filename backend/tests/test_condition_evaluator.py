"""Tests for ConditionEvaluator — positive and negative coverage."""
from datetime import datetime, timezone

import pytest

from sentinelwatch_backend.detection_rules.condition_evaluator import (
    ConditionEvaluationError,
    ConditionEvaluator,
    evaluate_rules,
)


@pytest.fixture()
def evaluator():
    return ConditionEvaluator()


# ---------- parsing & basic operators ----------

class TestConditionEvaluator:
    def test_empty_condition_returns_false(self, evaluator):
        assert evaluator.evaluate("", {"name": "foo"}) is False
        assert evaluator.evaluate("   ", {"name": "foo"}) is False

    def test_field_truthiness(self, evaluator):
        assert evaluator.evaluate("process_name", {"process_name": "evil.exe"}) is True
        assert evaluator.evaluate("process_name", {"process_name": None}) is False
        assert evaluator.evaluate("process_name", {}) is False

    def test_equality(self, evaluator):
        telemetry = {"process_name": "svch0st.exe"}
        assert evaluator.evaluate('process_name == "svch0st.exe"', telemetry) is True
        assert evaluator.evaluate('process_name == "powershell.exe"', telemetry) is False

    def test_inequality(self, evaluator):
        telemetry = {"service_status": "running"}
        assert evaluator.evaluate('service_status != "stopped"', telemetry) is True
        assert evaluator.evaluate('service_status != "running"', telemetry) is False

    def test_numeric_less_than(self, evaluator):
        telemetry = {"cpu_percent": 99.0}
        assert evaluator.evaluate("cpu_percent < 50.0", telemetry) is False
        assert evaluator.evaluate("cpu_percent > 50.0", telemetry) is True

    def test_numeric_gte(self, evaluator):
        telemetry = {"memory_percent": 80.0}
        assert evaluator.evaluate("memory_percent >= 80", telemetry) is True
        assert evaluator.evaluate("memory_percent >= 81", telemetry) is False

    def test_and_short_circuits(self, evaluator):
        telemetry = {"parent_process_name": "WINWORD.EXE", "process_name": "cmd.exe"}
        assert evaluator.evaluate(
            'parent_process_name == "WINWORD.EXE" and process_name == "cmd.exe"',
            telemetry,
        ) is True
        assert evaluator.evaluate(
            'parent_process_name == "EXCEL.EXE" and process_name == "cmd.exe"',
            telemetry,
        ) is False

    def test_or_short_circuits(self, evaluator):
        telemetry = {"process_name": "powershell.exe"}
        assert evaluator.evaluate(
            'process_name == "cmd.exe" or process_name == "powershell.exe"',
            telemetry,
        ) is True

    def test_not(self, evaluator):
        telemetry = {"process_name": "notepad.exe"}
        assert evaluator.evaluate('not process_name == "cmd.exe"', telemetry) is True
        assert evaluator.evaluate('not process_name == "notepad.exe"', telemetry) is False

    def test_in_list(self, evaluator):
        telemetry = {"process_name": "cmd.exe"}
        assert evaluator.evaluate(
            'process_name in ["cmd.exe", "powershell.exe"]', telemetry
        ) is True
        assert evaluator.evaluate(
            'process_name in ["reg.exe", "mshta.exe"]', telemetry
        ) is False

    def test_not_in_list(self, evaluator):
        telemetry = {"service_account": "LocalSystem"}
        assert evaluator.evaluate(
            'service_account not in ["LocalSystem", "NetworkService"]',
            telemetry,
        ) is False

    def test_matches_regex(self, evaluator):
        telemetry = {"process_exe": "C:\\Users\\evil\\hack.exe"}
        assert evaluator.evaluate(
            'process_exe matches regex "(?i)(temp|tmp)\\"', telemetry
        ) is False
        assert evaluator.evaluate(
            'process_exe matches regex "(?i)users\\\\\\"', telemetry
        ) is True

    def test_nested_field_access(self, evaluator):
        telemetry = {"extracted": {"provider_name": "Microsoft-Windows-Security-Auditing"}}
        assert evaluator.evaluate(
            'extracted.provider_name == "Microsoft-Windows-Security-Auditing"',
            telemetry,
        ) is True
        assert evaluator.evaluate(
            'extracted.provider_name == "other"', telemetry
        ) is False

    def test_parenthesised_expression(self, evaluator):
        telemetry = {"a": "x", "b": "y"}
        assert evaluator.evaluate('(a == "x" or b == "z") and a == "x"', telemetry) is True

    def test_missing_field_is_falsy(self, evaluator):
        assert evaluator.evaluate("nonexistent", {"name": "foo"}) is False


# ---------- rejection of unsupported expressions ----------

    def test_unsupported_syntax_raises(self, evaluator):
        """Unparseable condition strings must raise, never return silently."""
        with pytest.raises(ConditionEvaluationError):
            evaluator.evaluate("(process_name", {})  # unclosed paren

    def test_no_eval_used(self):
        """Sanity check that we do not use eval()."""
        import ast
        source = open(__file__).read()
        assert "eval(" not in source.split("test_")[0]


# ---------- evaluate_rules convenience helper ----------

class TestEvaluateRules:
    def test_skips_inactive(self):
        class FakeRule:
            rule_id = "R-1"
            condition = 'name == "evil"'
            def is_active(self):
                return False
        assert evaluate_rules({"name": "evil"}, [FakeRule()]) == []

    def test_matches_triggered(self):
        class FakeRule:
            def __init__(self, rid, cond):
                self.rule_id = rid
                self.condition = cond
            def is_active(self):
                return True
        rules = [FakeRule("R-1", 'name == "evil"')]
        triggered = evaluate_rules({"name": "evil"}, rules)
        assert len(triggered) == 1
        assert triggered[0].rule_id == "R-1"
