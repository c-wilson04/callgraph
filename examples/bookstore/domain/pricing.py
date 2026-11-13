"""Price calculation: discounts, tiers and tax."""

TAX_RATE = 0.0825
DISCOUNTS = {"fiction": 0.10, "poetry": 0.15}


def price_for(book, tier):
    price = book["price"]
    price = apply_discounts(price, book["genre"], tier)
    return add_tax(price)


def apply_discounts(price, genre, tier):
    price *= 1 - DISCOUNTS.get(genre, 0.0)
    if tier == "gold":
        price *= 0.95
    return round(price, 2)


def add_tax(price):
    return round(price * (1 + TAX_RATE), 2)
