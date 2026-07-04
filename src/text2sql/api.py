"""FastAPI service for the text-to-SQL interface."""

from __future__ import annotations

import os
import sqlite3
import time

from fastapi import FastAPI
from pydantic import BaseModel

from .generator import generate
from .guardrails import check
from .schema import introspect, relevant_tables, render_for_prompt
from .validator import validate

DB_PATH = os.environ.get("DB_PATH", "demo.db")

app = FastAPI(title="Text-to-SQL with Guardrails", version="1.0.0")
history: list[dict] = []


def connection() -> sqlite3.Connection:
    # Read-only sandbox: the URI mode blocks writes at the database layer
    # even if a guardrail rule were bypassed.
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


class QueryRequest(BaseModel):
    question: str


@app.post("/v1/query")
def query(request: QueryRequest):
    conn = connection()
    entry: dict = {"question": request.question, "timestamp": time.time()}

    generation = generate(request.question)
    if generation is None:
        entry["outcome"] = "not_understood"
        history.append(entry)
        return {"error": "could not map the question to SQL; try rephrasing",
                "clarification": "supported intents include counts, revenue,"
                                 " top customers, refund rate, and monthly"
                                 " order volumes"}

    guard = check(generation.sql)
    if not guard.allowed:
        entry.update({"outcome": "blocked", "violations": guard.violations})
        history.append(entry)
        return {"blocked": True, "violations": guard.violations,
                "sql": generation.sql}

    start = time.perf_counter()
    cursor = conn.execute(guard.sql)
    columns = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    elapsed = time.perf_counter() - start

    validation = validate(request.question, generation, rows, columns, conn)
    entry.update({"outcome": "executed", "sql": guard.sql,
                  "rows": len(rows), "confidence": validation.confidence,
                  "hallucination_flag": validation.hallucination_flag})
    history.append(entry)
    return {
        "sql": guard.sql,
        "explanation": generation.explanation,
        "columns": columns,
        "rows": rows[:100],
        "row_count": len(rows),
        "execution_ms": round(elapsed * 1000, 2),
        "confidence": validation.confidence,
        "hallucination_flag": validation.hallucination_flag,
        "back_translation": validation.back_translation,
        "alignment": validation.alignment,
        "sanity_flags": validation.sanity_flags,
        "multi_query_agreement": validation.agreement,
        "guardrail_modified": guard.modified,
    }


@app.get("/v1/schema")
def schema():
    conn = connection()
    full = introspect(conn)
    return {"schema": full,
            "prompt_rendering": render_for_prompt(full, list(full["tables"]))}


@app.get("/v1/history")
def get_history():
    return history[-100:]
