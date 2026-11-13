"""Catalog service: book lookups go through the cache."""


class CatalogService:
    def __init__(self, db, cache):
        self.db = db
        self.cache = cache

    def get_book(self, book_id):
        cached = self.cache.get(("book", book_id))
        if cached is not None:
            return cached
        book = self.db.get_book(book_id)
        if book is not None:
            self.cache.put(("book", book_id), book)
        return book

    def list_books(self, genre=None, page=1, per_page=20):
        rows = self.db.query_books(lambda row: genre is None or row["genre"] == genre)
        return list(paginate(rows, page, per_page))


def paginate(rows, page, per_page):
    start = (page - 1) * per_page
    for row in rows[start : start + per_page]:
        yield summarize(row)


def summarize(row):
    return {"id": row["id"], "title": row["title"], "price": row["price"]}
