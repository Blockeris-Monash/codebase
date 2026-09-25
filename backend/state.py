"""A dict that forgets, for the state the live mailbox keeps in memory.

Checked emails, the originals a reply threads under and failure counts used to grow with
every message the service ever saw, bodies included, for the life of the process (#147 B4).
One process holds all of it; sharing it between processes is #139.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterator, MutableMapping
from typing import Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class BoundedStore(MutableMapping[K, V], Generic[K, V]):
    """Entries expire `ttl` seconds after they were last written or read, and past `cap`
    entries the least recently used goes first. Not thread-safe: the event loop owns it."""

    def __init__(self, ttl: float, cap: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.ttl, self.cap, self._clock = ttl, cap, clock
        self._items: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def _expire(self) -> None:
        cutoff = self._clock() - self.ttl
        while self._items and next(iter(self._items.values()))[0] < cutoff:
            self._items.popitem(last=False)

    def __getitem__(self, key: K) -> V:
        self._expire()
        _, value = self._items[key]
        self._items[key] = (self._clock(), value)
        self._items.move_to_end(key)
        return value

    def __setitem__(self, key: K, value: V) -> None:
        self._items[key] = (self._clock(), value)
        self._items.move_to_end(key)
        self._expire()
        while len(self._items) > self.cap:
            self._items.popitem(last=False)

    def __delitem__(self, key: K) -> None:
        del self._items[key]

    def __iter__(self) -> Iterator[K]:
        self._expire()
        return iter(list(self._items))

    def __len__(self) -> int:
        self._expire()
        return len(self._items)
