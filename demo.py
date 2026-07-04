#!/usr/bin/env python3
"""Offline end-to-end demo: seed DB, run the golden eval suite."""

from __future__ import annotations

import json
import sqlite3
import sys

sys.path.insert(0, "src")

import seed
from text2sql.generator import generate
from text2sql.guardrails import check
from text2sql.validator import validate


def main() -> None:
    seed.build("demo.db")
    conn = sqlite3.connect("file:demo.db?mode=ro", uri=True)

    with open("data/golden_queries.json", encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]

    passed = 0
    unsafe_executed = 0
    for case in cases:
        question = case["question"]
        generation = generate(question)
        print(f"[{case['id']}] {question}")

        if generation is None:
            outcome = "not_translated_or_blocked"
            print("  -> not translated (no safe SQL mapping)")
        else:
            guard = check(generation.sql)
            if not guard.allowed:
                outcome = "not_translated_or_blocked"
                print(f"  -> BLOCKED: {guard.violations}")
            else:
                cursor = conn.execute(guard.sql)
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                validation = validate(question, generation, rows, columns,
                                      conn)
                outcome = ("hallucination_flagged"
                           if validation.hallucination_flag else "executes")
                print(f"  sql: {guard.sql[:88]}...")
                print(f"  rows={len(rows)} confidence={validation.confidence}"
                      f" alignment={validation.alignment}"
                      f" agreement={validation.agreement}")
                if validation.hallucination_flag:
                    print(f"  HALLUCINATION FLAG: SQL answers"
                          f" '{validation.back_translation}'")
                if not case["answers_right_question"]:
                    unsafe_executed += outcome == "executes"

        ok = outcome == case["expect"]
        passed += ok
        print(f"  expected={case['expect']} got={outcome}"
              f" {'PASS' if ok else 'FAIL'}\n")

    print(f"Eval: {passed}/{len(cases)} cases behaved as expected;"
          f" {unsafe_executed} unsafe queries executed")


if __name__ == "__main__":
    main()
