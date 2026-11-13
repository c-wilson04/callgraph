"""A tiny in-memory 'database' with a table scan and a primary-key lookup.

Every query pays a simulated network round-trip (like a real Postgres/MySQL call),
unless latency is turned off with ``app.py --no-latency``.
"""

import random
import time

ROUNDTRIP_SECONDS = 0.0003

GENRES = ["fiction", "science", "history", "fantasy", "biography", "poetry"]
WORDS = (
    "the of dragon river empire quantum garden silent winter secret city machine "
    "ocean history light shadow storm mind code journey star kingdom memory fire"
).split()


class Database:
    def __init__(self, seed: int = 7, n_books: int = 300, n_users: int = 60):
        rng = random.Random(seed)
        self.books = {}
        for book_id in range(1, n_books + 1):
            title = " ".join(rng.choice(WORDS) for _ in range(rng.randint(2, 5))).title()
            self.books[book_id] = {
                "id": book_id,
                "title": title,
                "genre": rng.choice(GENRES),
                "price": round(rng.uniform(6, 48), 2),
                "stock": rng.randint(0, 25),
                "description": " ".join(rng.choice(WORDS) for _ in range(40)),
            }
        self.users = {
            uid: {"id": uid, "history": rng.sample(range(1, n_books + 1), 6), "tier": rng.choice(["basic", "gold"])}
            for uid in range(1, n_users + 1)
        }
        self.orders = []
        self.latency = ROUNDTRIP_SECONDS

    def _roundtrip(self):
        if self.latency:
            time.sleep(self.latency)

    def get_book(self, book_id):
        self._roundtrip()
        return self.books.get(book_id)

    def query_books(self, predicate):
        """Full table scan - every row is checked."""
        self._roundtrip()
        return [row for row in self.books.values() if predicate(row)]

    def get_user(self, user_id):
        self._roundtrip()
        return self.users.get(user_id)

    def insert_order(self, order):
        self._roundtrip()
        order["id"] = len(self.orders) + 1
        self.orders.append(order)
        return order["id"]
