"""A small LRU cache in front of the database."""

from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity: int = 64):
        self.capacity = capacity
        self._items = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key):
        if key in self._items:
            self._items.move_to_end(key)
            self.hits += 1
            return self._items[key]
        self.misses += 1
        return None

    def put(self, key, value):
        self._items[key] = value
        self._items.move_to_end(key)
        if len(self._items) > self.capacity:
            self._evict()

    def _evict(self):
        self._items.popitem(last=False)
