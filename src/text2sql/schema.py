"""Database schema introspection with sample values and FK graph."""

from __future__ import annotations

import re
import sqlite3


def introspect(conn: sqlite3.Connection) -> dict:
    schema: dict = {"tables": {}}
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
        " AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        columns = []
        for cid, name, ctype, notnull, default, pk in conn.execute(
                f"PRAGMA table_info({table})"):
            columns.append({"name": name, "type": ctype, "pk": bool(pk)})
        fks = [{"column": row[3], "references": f"{row[2]}.{row[4]}"}
               for row in conn.execute(f"PRAGMA foreign_key_list({table})")]
        samples = {}
        for column in columns:
            if column["type"] == "TEXT":
                values = [r[0] for r in conn.execute(
                    f"SELECT DISTINCT {column['name']} FROM {table} LIMIT 5")]
                samples[column["name"]] = values
        schema["tables"][table] = {"columns": columns, "foreign_keys": fks,
                                   "samples": samples}
    return schema


def relevant_tables(schema: dict, question: str) -> list[str]:
    """Lightweight relevance filter: score tables by mention of their name,
    columns, or sample values in the question."""
    lowered = question.lower()
    scores = {}
    for table, info in schema["tables"].items():
        score = 0
        if table.rstrip("s") in lowered or table in lowered:
            score += 2
        for column in info["columns"]:
            if column["name"] in lowered:
                score += 1
        for values in info["samples"].values():
            score += sum(1 for v in values
                         if isinstance(v, str) and v.lower() in lowered)
        scores[table] = score
    picked = [t for t, s in scores.items() if s > 0]
    return picked or list(schema["tables"])


def render_for_prompt(schema: dict, tables: list[str]) -> str:
    lines = []
    for table in tables:
        info = schema["tables"][table]
        columns = ", ".join(f"{c['name']} {c['type']}"
                            for c in info["columns"])
        lines.append(f"TABLE {table} ({columns})")
        for fk in info["foreign_keys"]:
            lines.append(f"  FK {table}.{fk['column']} -> {fk['references']}")
    return "\n".join(lines)
