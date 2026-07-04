"""NL-to-SQL generation.

The offline generator maps question intents to SQL over the demo commerce
schema deterministically, including a planted failure mode: questions about
"average order value" are translated to average item price instead, which
the back-translation validator catches. With OPENAI_API_KEY set, generation
goes through an LLM given the same relevance-filtered schema prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Generation:
    sql: str
    explanation: str
    intent: str
    confidence: float
    tables: list[str] = field(default_factory=list)
    alternative_sql: str | None = None


RULES = [
    # (intent, pattern, sql, alternative sql for multi-query validation)
    ("count_customers", r"how many customers",
     "SELECT COUNT(*) AS customers FROM customers",
     "SELECT COUNT(DISTINCT id) FROM customers"),
    ("count_orders_completed", r"how many (completed )?orders",
     "SELECT COUNT(*) AS orders FROM orders WHERE status = 'completed'",
     "SELECT COUNT(id) FROM orders WHERE status = 'completed'"),
    ("revenue_total", r"total revenue",
     "SELECT ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue"
     " FROM order_items oi JOIN orders o ON o.id = oi.order_id"
     " WHERE o.status = 'completed'",
     "SELECT ROUND(SUM(t.line), 2) FROM (SELECT oi.quantity * oi.unit_price"
     " AS line FROM order_items oi JOIN orders o ON o.id = oi.order_id"
     " WHERE o.status = 'completed') t"),
    ("revenue_by_country", r"revenue by country",
     "SELECT c.country, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue"
     " FROM order_items oi JOIN orders o ON o.id = oi.order_id"
     " JOIN customers c ON c.id = o.customer_id"
     " WHERE o.status = 'completed' GROUP BY c.country ORDER BY revenue DESC",
     None),
    ("top_customers", r"top (\d+) customers",
     "SELECT c.name, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS spend"
     " FROM order_items oi JOIN orders o ON o.id = oi.order_id"
     " JOIN customers c ON c.id = o.customer_id"
     " WHERE o.status = 'completed' GROUP BY c.id ORDER BY spend DESC"
     " LIMIT {n}",
     None),
    ("orders_in_month", r"orders (were placed |placed )?in (january|february"
     r"|march|april|may|june)",
     "SELECT COUNT(*) AS orders FROM orders"
     " WHERE order_date LIKE '2026-{month:02d}-%'",
     "SELECT COUNT(id) FROM orders WHERE order_date >= '2026-{month:02d}-01'"
     " AND order_date <= '2026-{month:02d}-31'"),
    ("refund_rate", r"(refund rate|percentage .*refunded)",
     "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'refunded' THEN 1 ELSE 0"
     " END) / COUNT(*), 2) AS refund_pct FROM orders",
     None),
    # Planted hallucination: answers a different question (avg item price,
    # not avg order value). Back-translation flags the mismatch.
    ("avg_order_value", r"average order value",
     "SELECT ROUND(AVG(unit_price), 2) AS avg_value FROM order_items",
     None),
]

MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
          "june": 6}


def generate(question: str) -> Generation | None:
    lowered = question.lower()
    for intent, pattern, sql, alternative in RULES:
        match = re.search(pattern, lowered)
        if not match:
            continue
        if intent == "top_customers":
            sql = sql.format(n=int(match.group(1)))
        if intent == "orders_in_month":
            month = MONTHS[match.group(2)]
            sql = sql.format(month=month)
            alternative = alternative.format(month=month)
        tables = sorted(set(re.findall(
            r"(?:FROM|JOIN)\s+([a-z_]+)", sql)))
        return Generation(
            sql=sql,
            explanation=f"Interpreted the question as intent"
                        f" '{intent}' over tables {', '.join(tables)}.",
            intent=intent,
            confidence=0.9 if intent != "avg_order_value" else 0.75,
            tables=tables,
            alternative_sql=alternative)
    return None


def back_translate(sql: str) -> str:
    """Describe what question the SQL actually answers.

    Offline this is rule-based over the SQL structure; live mode asks an
    LLM 'what question does this SQL answer?'. The validator compares the
    result against the user's question.
    """
    lowered = sql.lower()
    if "avg(unit_price)" in lowered:
        return "what is the average price of individual line items"
    if "sum(oi.quantity * oi.unit_price)" in lowered and "group by c.country" in lowered:
        return "what is the total revenue grouped by customer country"
    if "sum(oi.quantity * oi.unit_price)" in lowered and "group by c.id" in lowered:
        return "which customers spent the most in total"
    if "sum(oi.quantity * oi.unit_price)" in lowered:
        return "what is the total revenue from completed orders"
    if "count(*)" in lowered and "from customers" in lowered:
        return "how many customers are there"
    if "refunded" in lowered and "100.0" in lowered:
        return "what percentage of orders were refunded"
    if "count(*)" in lowered and "order_date like" in lowered:
        return "how many orders were placed in a given month"
    if "count(*)" in lowered and "from orders" in lowered:
        return "how many completed orders are there"
    return "unclear what question this SQL answers"
