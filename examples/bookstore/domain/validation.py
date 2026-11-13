"""Request validation."""


class ValidationError(Exception):
    pass


def validate_order(payload, db):
    if not payload.get("items"):
        raise ValidationError("order has no items")
    for item in payload["items"]:
        validate_item(item, db)
    return True


def validate_item(item, db):
    book = db.get_book(item["book_id"])
    if book is None:
        raise ValidationError(f"unknown book {item['book_id']}")
    if item["qty"] > book["stock"]:
        raise ValidationError(f"only {book['stock']} left of book {book['id']}")
