# Text-to-SQL Interface with Guardrails and Hallucination Detection

A natural language interface that translates plain English questions into SQL against a real database, executes them safely behind guardrails that block destructive operations, validates that the generated SQL actually answers the question asked, and presents results with a composite confidence score.

Live demo: https://mansimengde17.github.io/Text-to-SQL-Interface-with-Guardrails-and-Hallucination-Detection/

## Why guardrails first

Text-to-SQL is one of the highest-value LLM applications in the enterprise, and the reason it rarely ships is safety, not accuracy. This system is built so a compliance team could approve it: zero write paths, bounded scans, full audit logging, and a hallucination detector that catches SQL answering the wrong question before the user sees the result.

## Architecture

```
    natural language question
              |
              v
 +---------------------------+
 |  Schema-aware prompt engine |  introspected tables, columns, FKs,
 |  relevance-filtered schema  |  sample values, few-shot examples
 +---------------------------+
              |
              v
 +---------------------------+
 |      SQL generation        |  SQL + explanation + confidence +
 +---------------------------+  tables/columns accessed
              |
              v
 +---------------------------+
 |     Guardrail middleware   |  blocks DDL and DML writes, enforces
 |                            |  LIMIT, caps subquery depth, single
 |                            |  statement only; every block logged
 +---------------------------+
              |
              v
 +---------------------------+
 |   Read-only sandboxed      |  read-only connection as second
 |   execution                |  line of defense
 +---------------------------+
              |
              v
 +---------------------------+
 |  Hallucination detection   |  back-translation alignment,
 |  and confidence scoring    |  result sanity checks, multi-query
 +---------------------------+  agreement
```

## Quick start (offline)

The repository seeds a SQLite commerce database (customers, products, orders, order_items) and includes a deterministic NL-to-SQL generator, so everything runs with no API key:

```bash
pip install -r requirements.txt
python demo.py
```

The demo runs the eval suite: correct translations, a blocked destructive request, and a planted hallucination caught by back-translation. Set `OPENAI_API_KEY` to replace the offline generator with LLM generation using the same schema-aware prompt.

To serve the API:

```bash
uvicorn src.text2sql.api:app --reload
# POST /v1/query    {"question": "..."} -> SQL, results, confidence, warnings
# GET  /v1/schema   introspected schema with sample values
# GET  /v1/history  audit trail of past queries
```

## Guardrail rules (all configurable)

- Block all DDL: CREATE, ALTER, DROP, TRUNCATE
- Block all DML writes: INSERT, UPDATE, DELETE, REPLACE
- Single statement only; statement stacking is rejected
- Enforce a row limit (LIMIT 1000 appended when missing)
- Reject subqueries nested deeper than 3 levels
- Execution uses a read-only connection, so even a bypassed rule cannot write

Every blocked query is logged with the rule that fired.

## Hallucination detection

1. Back-translation: the generated SQL is translated back into a question and compared with the original. Low alignment means the SQL answers a different question than the one asked; it is flagged instead of silently returned.
2. Result sanity checks: aggregates checked against plausible ranges, date ranges checked against the data's timespan, NULL-heavy columns flagged as possible bad JOINs.
3. Multi-query agreement: for aggregate questions, a second SQL formulation is generated independently and both are executed; disagreement drops confidence and surfaces both results.

The composite confidence combines syntax validity, back-translation alignment, sanity check pass rate, and multi-query agreement.

## Repository layout

```
src/text2sql/schema.py      introspection with sample values and FK graph
src/text2sql/generator.py   NL-to-SQL generation (offline + LLM hook)
src/text2sql/guardrails.py  safety middleware
src/text2sql/validator.py   back-translation, sanity checks, agreement
src/text2sql/api.py         FastAPI service
seed.py                     builds the demo commerce database
data/golden_queries.json    eval suite
demo.py                     offline end-to-end run
tests/
```
