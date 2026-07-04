"""Hallucination detection and confidence scoring."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from .generator import Generation, back_translate

STOPWORDS = {"what", "is", "the", "of", "a", "an", "are", "there", "in",
             "were", "was", "how", "by", "for", "to", "from", "and", "which",
             "do", "does", "did", "this", "that", "with", "total", "given"}


SYNONYMS = {"percentage": "rate", "spent": "spend", "most": "top",
            "buyers": "customer", "purchases": "order"}


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _terms(text: str) -> set[str]:
    words = set(re.findall(r"[a-z]+", text.lower())) - STOPWORDS
    return {_stem(SYNONYMS.get(w, w)) for w in words}


@dataclass
class Validation:
    back_translation: str
    alignment: float
    sanity_flags: list[str] = field(default_factory=list)
    agreement: bool | None = None
    confidence: float = 0.0
    hallucination_flag: bool = False


def alignment_score(question: str, translated: str) -> float:
    q, t = _terms(question), _terms(translated)
    if not q or not t:
        return 0.0
    # Recall of the question's content terms in the back-translation: the
    # question is the contract; extra detail in the translation is fine.
    return len(q & t) / len(q)


def sanity_checks(rows: list[tuple], columns: list[str],
                  conn: sqlite3.Connection) -> list[str]:
    flags: list[str] = []
    if not rows:
        flags.append("query returned zero rows")
        return flags
    for i, column in enumerate(columns):
        values = [r[i] for r in rows]
        nulls = sum(v is None for v in values)
        if nulls / len(values) > 0.5:
            flags.append(f"column '{column}' is more than 50 percent NULL"
                         " (possible bad JOIN)")
        numeric = [v for v in values if isinstance(v, (int, float))]
        if numeric and any(v < 0 for v in numeric) and \
                re.search(r"revenue|spend|count|quantity|pct", column):
            flags.append(f"column '{column}' contains negative values")
        if "pct" in column and numeric and any(v > 100 for v in numeric):
            flags.append(f"percentage column '{column}' exceeds 100")
    return flags


def multi_query_agreement(conn: sqlite3.Connection, primary_rows: list[tuple],
                          alternative_sql: str | None) -> bool | None:
    if not alternative_sql:
        return None
    alt_rows = conn.execute(alternative_sql).fetchall()
    def scalar(rows):
        return rows[0][0] if rows and len(rows[0]) >= 1 else None
    return scalar(primary_rows) == scalar(alt_rows)


def validate(question: str, generation: Generation, rows: list[tuple],
             columns: list[str], conn: sqlite3.Connection,
             alignment_floor: float = 0.45) -> Validation:
    translated = back_translate(generation.sql)
    alignment = alignment_score(question, translated)
    flags = sanity_checks(rows, columns, conn)
    agreement = multi_query_agreement(conn, rows, generation.alternative_sql)

    confidence = (0.25                                    # valid syntax
                  + 0.35 * min(1.0, alignment / 0.6)      # back-translation
                  + 0.25 * (1.0 - min(1.0, len(flags) / 2))
                  + (0.15 if agreement in (True, None) else 0.0))
    hallucination = alignment < alignment_floor or agreement is False
    return Validation(back_translation=translated,
                      alignment=round(alignment, 3),
                      sanity_flags=flags,
                      agreement=agreement,
                      confidence=round(min(confidence, 0.99), 3),
                      hallucination_flag=hallucination)
