"""Full-text search.

Deliberately naive: every query re-tokenizes every book's description instead of
using an index. This is the kind of hotspot callgraph makes obvious.
"""


def search_books(db, query, limit=5):
    terms = tokenize(query)
    scored = []
    for book in db.query_books(lambda row: True):
        s = score(book, terms)
        if s > 0:
            scored.append((s, book["id"]))
    scored.sort(reverse=True)
    return [book_id for _, book_id in scored[:limit]]


def score(book, terms):
    words = tokenize(book["title"] + " " + book["description"])
    return sum(words.count(term) for term in terms)


def tokenize(text):
    return [normalize(word) for word in text.split()]


def normalize(word):
    return word.lower().strip(".,!?")
