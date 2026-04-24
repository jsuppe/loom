"""Reference implementation of TaskQueue.

Never shown to either agent. Lives here so we can quickly verify the
ground-truth tests are internally consistent (run `pytest` against this
plus the test file and expect 15/15 green).
"""
from __future__ import annotations

from typing import Callable


class TaskQueue:
    def __init__(self) -> None:
        self._items: list[tuple[int, int, str, int]] = []  # (neg_priority, seq, name, priority)
        self._seq = 0

    def add(self, name: str, priority: int = 0) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("name must be a non-empty string")
        self._items.append((-priority, self._seq, name, priority))
        self._seq += 1
        self._items.sort()

    def pop(self) -> tuple[str, int]:
        if not self._items:
            raise IndexError("pop from an empty TaskQueue")
        _, _, name, priority = self._items.pop(0)
        return (name, priority)

    def peek(self) -> tuple[str, int] | None:
        if not self._items:
            return None
        _, _, name, priority = self._items[0]
        return (name, priority)

    def cancel(self, name: str) -> bool:
        for i, (_, _, n, _p) in enumerate(self._items):
            if n == name:
                self._items.pop(i)
                return True
        return False

    def filter(self, predicate: Callable[[tuple[str, int]], bool]) -> list[tuple[str, int]]:
        return [
            (name, priority)
            for _, _, name, priority in self._items
            if predicate((name, priority))
        ]

    def __len__(self) -> int:
        return len(self._items)
