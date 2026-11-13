"""Order placement."""

from domain.pricing import price_for
from domain.validation import validate_order


class OrderService:
    def __init__(self, db, catalog):
        self.db = db
        self.catalog = catalog

    def place_order(self, user_id, payload):
        user = self.db.get_user(user_id)
        validate_order(payload, self.db)
        total = 0.0
        for item in payload["items"]:
            book = self.catalog.get_book(item["book_id"])
            total += price_for(book, user["tier"]) * item["qty"]
            reserve_stock(book, item["qty"])
        return self.db.insert_order({"user": user_id, "items": payload["items"], "total": round(total, 2)})


def reserve_stock(book, qty):
    book["stock"] -= qty
