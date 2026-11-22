"""Helpers for the .sql files: placeholder rendering, statement splitting, named queries.

Rules the SQL files follow so these helpers stay simple: no ';' inside string literals,
no trailing '--' comments on code lines (full-line comments only).
"""
import re
from collections import OrderedDict

_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
_NAME_MARKER = re.compile(r"^--\s*name:\s*(\w+)\s*$", re.MULTILINE)


def render(sql, params):
    """Replace {{NAME}} placeholders. Unknown or missing placeholders raise KeyError."""
    def sub(match):
        key = match.group(1)
        if key not in params:
            raise KeyError("SQL placeholder {{%s}} has no value" % key)
        return str(params[key])
    return _PLACEHOLDER.sub(sub, sql)


def placeholders(sql):
    return set(_PLACEHOLDER.findall(sql))


def split_statements(sql):
    """Split a script into statements; full-line '--' comments are dropped."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def parse_named_queries(sql):
    """Return OrderedDict name -> single SQL statement (without trailing ';')."""
    marks = list(_NAME_MARKER.finditer(sql))
    out = OrderedDict()
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(sql)
        stmts = split_statements(sql[m.end():end])
        if len(stmts) != 1:
            raise ValueError("query %s must hold exactly one statement" % m.group(1))
        out[m.group(1)] = stmts[0]
    return out
