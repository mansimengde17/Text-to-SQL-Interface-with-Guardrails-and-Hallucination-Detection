import sqlite3
import sys
import unittest

sys.path.insert(0, "src")
sys.path.insert(0, ".")

import seed
from text2sql.generator import generate
from text2sql.guardrails import check
from text2sql.validator import validate


class GuardrailTests(unittest.TestCase):
    def test_blocks_dml(self):
        for sql in ("DELETE FROM customers", "UPDATE orders SET status='x'",
                    "INSERT INTO t VALUES (1)", "DROP TABLE customers"):
            self.assertFalse(check(sql).allowed)

    def test_blocks_statement_stacking(self):
        result = check("SELECT 1; DROP TABLE customers")
        self.assertFalse(result.allowed)

    def test_appends_limit(self):
        result = check("SELECT * FROM customers")
        self.assertTrue(result.allowed)
        self.assertIn("LIMIT 1000", result.sql)
        self.assertTrue(result.modified)

    def test_keyword_in_string_literal_ok(self):
        result = check("SELECT * FROM orders WHERE status = 'deleted'")
        self.assertTrue(result.allowed)


class ValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed.build("test_demo.db")
        cls.conn = sqlite3.connect("file:test_demo.db?mode=ro", uri=True)

    def _run(self, question):
        generation = generate(question)
        guard = check(generation.sql)
        cursor = self.conn.execute(guard.sql)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        return validate(question, generation, rows, columns, self.conn)

    def test_correct_translation_high_confidence(self):
        validation = self._run("What is the total revenue?")
        self.assertFalse(validation.hallucination_flag)
        self.assertGreaterEqual(validation.confidence, 0.7)

    def test_planted_hallucination_is_flagged(self):
        validation = self._run("What is the average order value?")
        self.assertTrue(validation.hallucination_flag)

    def test_multi_query_agreement_true(self):
        validation = self._run("How many customers do we have?")
        self.assertTrue(validation.agreement)

    def test_destructive_request_not_translated(self):
        self.assertIsNone(generate("Delete all customers from Germany"))


if __name__ == "__main__":
    unittest.main()
