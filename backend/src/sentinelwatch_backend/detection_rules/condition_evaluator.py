"""Condition Evaluator for SentinelWatch Detection Rules.

Parses and evaluates CEL-like condition expressions against telemetry data.
Supports operators: matches regex, in, not in, ==, !=, <, >, <=, >=, and, or, not
"""

import re
import operator
from typing import Any, Dict, List, Optional, Union
from functools import lru_cache


class ConditionEvaluationError(Exception):
    """Raised when condition evaluation fails."""
    pass


class ConditionEvaluator:
    """Evaluates CEL-like condition expressions against telemetry data."""

    # Operator mappings
    BINARY_OPS = {
        '==': operator.eq,
        '!=': operator.ne,
        '<': operator.lt,
        '<=': operator.le,
        '>': operator.gt,
        '>=': operator.ge,
        'in': lambda a, b: a in b if hasattr(b, '__contains__') else False,
        'not in': lambda a, b: a not in b if hasattr(b, '__contains__') else True,
        'and': lambda a, b: bool(a) and bool(b),
        'or': lambda a, b: bool(a) or bool(b),
    }

    UNARY_OPS = {
        'not': lambda a: not bool(a),
    }

    def __init__(self):
        self._regex_cache: Dict[str, re.Pattern] = {}

    def evaluate(self, condition: str, telemetry: Dict[str, Any]) -> bool:
        """Evaluate a condition string against telemetry data."""
        if not condition or not condition.strip():
            return False

        parsed = self._parse(condition)
        result = self._evaluate_ast(parsed, telemetry)
        # Top-level result is always coerced to bool so standalone field
        # references like 'process_name' evaluate to truthiness.
        return bool(result)

    def _parse(self, condition: str) -> Any:
        """Parse condition string into AST."""
        # Simple recursive descent parser for our condition language
        tokens = self._tokenize(condition)
        return self._parse_expression(tokens, 0)[0]

    def _tokenize(self, condition: str) -> List[str]:
        """Tokenize condition string."""
        # NOTE: this pattern deliberately avoids re.VERBOSE because VERBOSE
        # ignores whitespace inside the pattern, which would break the
        # multi-word operators 'not in' and 'matches regex'.
        # 'not in' and 'matches regex' must appear BEFORE 'not' and 'in'
        # so the longer alternatives win the alternation.
        token_pattern = re.compile(
            r'(==|!=|<=|>=|<|>|and|or|not[ ]in|matches[ ]regex|not|in)'  # operators
            r'|(\[)'                                                   # list start
            r'|(\])'                                                   # list end
            r'|(,)'                                                    # comma
            r'|("[^"]*")'                                             # double-quoted strings
            r"|('[^']*')"                                             # single-quoted strings
            r'|(\d+\.?\d*)'                                           # numbers
            r'|([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)*)'          # identifiers with dotted paths
            r'|([()])'                                                # parentheses
        , re.IGNORECASE)

        tokens = token_pattern.findall(condition)
        # Flatten tuples and filter out empty strings
        flat_tokens = []
        for match_tuple in tokens:
            for group in match_tuple:
                if group:
                    flat_tokens.append(group)
        return [t for t in flat_tokens if t.strip()]

    def _parse_expression(self, tokens: List[str], pos: int) -> tuple:
        """Parse expression with operator precedence."""
        # Precedence: or < and < not < comparison < primary
        return self._parse_or(tokens, pos)

    def _parse_or(self, tokens: List[str], pos: int) -> tuple:
        left, pos = self._parse_and(tokens, pos)
        while pos < len(tokens) and tokens[pos].lower() == 'or':
            op = tokens[pos]
            pos += 1
            right, pos = self._parse_and(tokens, pos)
            left = ('or', left, right)
        return left, pos

    def _parse_and(self, tokens: List[str], pos: int) -> tuple:
        left, pos = self._parse_not(tokens, pos)
        while pos < len(tokens) and tokens[pos].lower() == 'and':
            op = tokens[pos]
            pos += 1
            right, pos = self._parse_not(tokens, pos)
            left = ('and', left, right)
        return left, pos

    def _parse_not(self, tokens: List[str], pos: int) -> tuple:
        # 'not in' is a single binary comparison operator, not a unary NOT
        # applied to an IN expression. Check for it first.
        if pos + 1 < len(tokens) and tokens[pos].lower() == 'not' and tokens[pos + 1].lower() == 'in':
            return self._parse_comparison(tokens, pos)
        if pos < len(tokens) and tokens[pos].lower() == 'not':
            op = tokens[pos]
            pos += 1
            operand, pos = self._parse_not(tokens, pos)
            return ('not', operand), pos
        return self._parse_comparison(tokens, pos)

    def _parse_comparison(self, tokens: List[str], pos: int) -> tuple:
        left, pos = self._parse_primary(tokens, pos)
        while pos < len(tokens):
            token = tokens[pos].lower()
            # Handle 'not in' — it can arrive either as a single token
            # (from the tokenizer) or as two separate tokens ('not' then 'in').
            if token == 'not in':
                op = 'not in'
                pos += 1
                right, pos = self._parse_primary(tokens, pos)
                left = (op, left, right)
            elif token == 'not' and pos + 1 < len(tokens) and tokens[pos + 1].lower() == 'in':
                op = 'not in'
                pos += 2
                right, pos = self._parse_primary(tokens, pos)
                left = (op, left, right)
            elif token in ('==', '!=', '<', '<=', '>', '>=', 'in', 'matches regex'):
                op = token
                pos += 1
                right, pos = self._parse_primary(tokens, pos)
                left = (op, left, right)
            else:
                break
        return left, pos

    def _parse_primary(self, tokens: List[str], pos: int) -> tuple:
        if pos >= len(tokens):
            raise ConditionEvaluationError("Unexpected end of expression")

        token = tokens[pos]

        # Parenthesized expression
        if token == '(':
            pos += 1
            expr, pos = self._parse_expression(tokens, pos)
            if pos >= len(tokens) or tokens[pos] != ')':
                raise ConditionEvaluationError("Expected ')'")
            return expr, pos + 1

        # List literal [...]
        if token == '[':
            pos += 1
            elements = []
            while pos < len(tokens) and tokens[pos] != ']':
                elem, pos = self._parse_primary(tokens, pos)
                elements.append(elem)
                if pos < len(tokens) and tokens[pos] == ',':
                    pos += 1  # Skip comma
            if pos >= len(tokens) or tokens[pos] != ']':
                raise ConditionEvaluationError("Expected ']'")
            return elements, pos + 1

        # String literal
        if (token.startswith('"') and token.endswith('"')) or \
           (token.startswith("'") and token.endswith("'")):
            return token[1:-1], pos + 1

        # Number
        try:
            if '.' in token:
                return float(token), pos + 1
            return int(token), pos + 1
        except ValueError:
            pass

        # Identifier (field access)
        return ('field', token), pos + 1

    def _evaluate_ast(self, node: Any, telemetry: Dict[str, Any]) -> Any:
        """Evaluate AST node against telemetry.

        Returns the raw value for field nodes and literals so that binary
        operators can compare them. Boolean operators short-circuit and
        return a bool. The top-level call to evaluate() wraps the result
        in bool().
        """
        if isinstance(node, tuple):
            op = node[0]

            if op in ('or', 'and'):
                left = self._evaluate_ast(node[1], telemetry)
                if op == 'or' and left:
                    return True
                if op == 'and' and not left:
                    return False
                return self._evaluate_ast(node[2], telemetry)

            elif op == 'not':
                return not self._evaluate_ast(node[1], telemetry)

            elif op == 'field':
                # Field access - return the raw value, not its truthiness.
                # Binary operators need the actual value for comparison.
                field_name = node[1]
                return self._get_field_value(telemetry, field_name)

            elif op in self.BINARY_OPS:
                left_val = self._evaluate_ast(node[1], telemetry)
                right_val = self._evaluate_ast(node[2], telemetry)

                # Special handling for 'matches regex'
                if op == 'matches regex':
                    return self._matches_regex(left_val, right_val)

                # Special handling for 'in' / 'not in'
                if op in ('in', 'not in'):
                    return self._eval_in_op(left_val, right_val, op)

                # Standard binary ops
                func = self.BINARY_OPS.get(op)
                if func:
                    try:
                        return bool(func(left_val, right_val))
                    except Exception:
                        # Reraise so callers know evaluation failed
                        raise

        # Literal value
        return node

    def _get_field_value(self, telemetry: Dict[str, Any], field: str) -> Any:
        """Get field value from telemetry, supporting nested access."""
        # Handle nested fields like process_exe, parent_process_name, etc.
        if field in telemetry:
            return telemetry[field]

        # Try nested access (e.g., process.exe -> telemetry['process']['exe'])
        if '.' in field:
            parts = field.split('.')
            current = telemetry
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            return current

        return None

    def _matches_regex(self, value: Any, pattern: str) -> bool:
        """Check if value matches regex pattern."""
        if value is None:
            return False

        value_str = str(value)
        try:
            if pattern not in self._regex_cache:
                self._regex_cache[pattern] = re.compile(pattern, re.IGNORECASE)
            return bool(self._regex_cache[pattern].search(value_str))
        except re.error:
            return False

    def _eval_in_op(self, left: Any, right: Any, op: str) -> bool:
        """Evaluate 'in' or 'not in' operator."""
        if right is None:
            return False

        # Convert right to iterable if not already
        if isinstance(right, str):
            right_iter = [s.strip() for s in right.split(',')]
        elif hasattr(right, '__iter__') and not isinstance(right, (str, bytes)):
            right_iter = list(right)
        else:
            right_iter = [right]

        if op == 'in':
            return left in right_iter
        else:  # 'not in'
            return left not in right_iter


def evaluate_rule_condition(rule: DetectionRule, telemetry: Dict[str, Any]) -> bool:
    """Convenience function to evaluate a single rule's condition."""
    evaluator = ConditionEvaluator()
    return evaluator.evaluate(rule.condition, telemetry)


def evaluate_rules(telemetry: Dict[str, Any], rules: list) -> list:
    """Evaluate multiple rules against telemetry.

    Raises any evaluation error so it is never silently hidden from callers.
    """
    evaluator = ConditionEvaluator()
    results = []
    for rule in rules:
        if rule.is_active():
            triggered = evaluator.evaluate(rule.condition, telemetry)
            if triggered:
                results.append(rule)
    return results
