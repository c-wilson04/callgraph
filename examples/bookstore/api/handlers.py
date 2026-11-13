"""Route handlers: thin glue between HTTP-style requests and the services."""

from api.router import Router, authenticate, rate_limit
from services.search import search_books


def build_app(db, catalog, orders, recommender):
    app = Router()
    app.use(authenticate)
    app.use(rate_limit)

    @app.route("GET", "/books")
    def list_books(request):
        return catalog.list_books(genre=request.get("genre"), page=request.get("page", 1))

    @app.route("GET", "/books/{book_id}")
    def get_book(request, book_id):
        return catalog.get_book(book_id)

    @app.route("GET", "/search")
    def search(request):
        ids = search_books(db, request["q"])
        return [catalog.get_book(book_id) for book_id in ids]

    @app.route("POST", "/orders")
    def create_order(request):
        return orders.place_order(request["user"], request["body"])

    @app.route("GET", "/users/{user_id}/recommendations")
    def recommendations(request, user_id):
        return recommender.recommend(user_id)

    return app
