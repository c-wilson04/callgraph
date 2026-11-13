"""Bookstore API demo: replays a deterministic batch of simulated HTTP requests.

    python app.py                 # run normally (400 requests)
    python app.py 1000            # more traffic
    python app.py --no-latency    # pure CPU: no simulated database round-trips
    callgraph run app.py          # see what actually executed
    callgraph run --format html --open app.py
"""

import random
import sys

from api.handlers import build_app
from data.cache import LRUCache
from data.db import Database
from services.catalog import CatalogService
from services.orders import OrderService
from services.recommend import Recommender


def create_app(latency=True):
    db = Database()
    if not latency:
        db.latency = 0
    cache = LRUCache(capacity=64)
    catalog = CatalogService(db, cache)
    orders = OrderService(db, catalog)
    recommender = Recommender(db, catalog)
    return build_app(db, catalog, orders, recommender), cache


def generate_traffic(n, seed=42):
    """A realistic mix: mostly browsing, some search, a few orders."""
    rng = random.Random(seed)
    for _ in range(n):
        user = rng.randint(1, 60)
        roll = rng.random()
        if roll < 0.45:
            req = {"method": "GET", "path": f"/books/{rng.randint(1, 120)}"}
        elif roll < 0.65:
            req = {"method": "GET", "path": "/books", "genre": rng.choice(["fiction", "science", None]), "page": rng.randint(1, 3)}
        elif roll < 0.77:
            req = {"method": "GET", "path": "/search", "q": rng.choice(["dragon", "quantum garden", "silent storm", "history of fire"])}
        elif roll < 0.90:
            req = {"method": "GET", "path": f"/users/{user}/recommendations"}
        else:
            items = [{"book_id": rng.randint(1, 320), "qty": rng.randint(1, 3)} for _ in range(rng.randint(1, 3))]
            req = {"method": "POST", "path": "/orders", "body": {"items": items}}
        req.update(user=user, token=None if rng.random() < 0.03 else "t0k3n")
        yield req


def main(n_requests=400, latency=True):
    app, cache = create_app(latency)
    statuses = {}
    for request in generate_traffic(n_requests):
        response = app.dispatch(request)
        statuses[response["status"]] = statuses.get(response["status"], 0) + 1
    print(f"served {n_requests} requests: {dict(sorted(statuses.items()))}")
    print(f"cache: {cache.hits} hits / {cache.misses} misses")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(int(args[0]) if args else 400, latency="--no-latency" not in sys.argv)
