#!/usr/bin/env python3
"""Seed the demo commerce database."""

from __future__ import annotations

import random
import sqlite3

SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL,
    signup_date TEXT NOT NULL);
CREATE TABLE products (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    price REAL NOT NULL);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL, unit_price REAL NOT NULL);
"""

COUNTRIES = ["US", "DE", "IN", "BR", "JP"]
CATEGORIES = ["electronics", "books", "apparel", "home"]
STATUSES = ["completed", "completed", "completed", "cancelled", "refunded"]
NAMES = ["Ava Chen", "Liam Patel", "Noah Kim", "Mia Lopez", "Emma Das",
         "Oliver Sato", "Sofia Ricci", "Ethan Wolf", "Isla Mori", "Leo Braun"]


def build(path: str = "demo.db", seed: int = 42) -> None:
    random.seed(seed)
    conn = sqlite3.connect(path)
    conn.executescript("DROP TABLE IF EXISTS order_items;"
                       "DROP TABLE IF EXISTS orders;"
                       "DROP TABLE IF EXISTS products;"
                       "DROP TABLE IF EXISTS customers;" + SCHEMA)
    for i in range(1, 61):
        conn.execute("INSERT INTO customers VALUES (?, ?, ?, ?)",
                     (i, f"{random.choice(NAMES)} {i}",
                      random.choice(COUNTRIES),
                      f"2025-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"))
    for i in range(1, 31):
        conn.execute("INSERT INTO products VALUES (?, ?, ?, ?)",
                     (i, f"Product {i}", random.choice(CATEGORIES),
                      round(random.uniform(5, 400), 2)))
    order_id = 0
    for _ in range(400):
        order_id += 1
        conn.execute("INSERT INTO orders VALUES (?, ?, ?, ?)",
                     (order_id, random.randint(1, 60),
                      f"2026-{random.randint(1, 6):02d}-{random.randint(1, 28):02d}",
                      random.choice(STATUSES)))
        for _ in range(random.randint(1, 4)):
            price = round(random.uniform(5, 400), 2)
            conn.execute(
                "INSERT INTO order_items (order_id, product_id, quantity,"
                " unit_price) VALUES (?, ?, ?, ?)",
                (order_id, random.randint(1, 30), random.randint(1, 5), price))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    build()
    print("Seeded demo.db")
