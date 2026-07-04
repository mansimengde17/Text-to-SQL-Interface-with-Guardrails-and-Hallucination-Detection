"""Guardrail middleware: every query passes through before execution."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BLOCKED_KEYWORDS = ("insert", "update", "delete", "drop", "create", "alter",
                    "truncate", "replace", "attach", "detach", "pragma",
                    "vacuum", "grant", "revoke")
DEFAULT_ROW_LIMIT = 1000
MAX_SUBQUERY_DEPTH = 3


@dataclass
class GuardrailResult:
    allowed: bool
    sql: str
    violations: list[str] = field(default_factory=list)
    modified: bool = False


def _strip_strings(sql: str) -> str:
    return re.sub(r"'[^']*'", "''", sql)


def check(sql: str, row_limit: int = DEFAULT_ROW_LIMIT,
          max_depth: int = MAX_SUBQUERY_DEPTH) -> GuardrailResult:
    violations: list[str] = []
    bare = _strip_strings(sql.strip().rstrip(";"))
    lowered = bare.lower()

    if ";" in bare:
        violations.append("statement stacking is not allowed")
    if not lowered.lstrip().startswith(("select", "with")):
        violations.append("only SELECT queries are allowed")
    for keyword in BLOCKED_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            violations.append(f"blocked keyword: {keyword.upper()}")

    depth = current = 0
    for char in bare:
        if char == "(":
            current += 1
            depth = max(depth, current)
        elif char == ")":
            current -= 1
    if depth > max_depth + 1:
        violations.append(f"subquery nesting deeper than {max_depth} levels")

    if violations:
        return GuardrailResult(False, sql, violations)

    modified = False
    if not re.search(r"\blimit\s+\d+\b", lowered):
        sql = f"{sql.rstrip().rstrip(';')} LIMIT {row_limit}"
        modified = True
    return GuardrailResult(True, sql, [], modified)
