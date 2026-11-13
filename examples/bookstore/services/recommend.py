"""Recommendations: walk 'similar book' links recursively."""


class Recommender:
    def __init__(self, db, catalog):
        self.db = db
        self.catalog = catalog

    def recommend(self, user_id, k=5):
        user = self.db.get_user(user_id)
        seen = set(user["history"])
        found = []
        for book_id in user["history"][:3]:
            self.expand(book_id, depth=2, seen=seen, found=found)
        return found[:k]

    def expand(self, book_id, depth, seen, found):
        if depth == 0:
            return
        book = self.catalog.get_book(book_id)
        for neighbor in similar_ids(book):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            found.append(neighbor)
            self.expand(neighbor, depth - 1, seen, found)


def similar_ids(book, n=3):
    base = book["id"]
    return [((base * 7 + i * 13) % 300) + 1 for i in range(n)]
