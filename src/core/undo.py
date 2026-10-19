"""Undo stack with bounded depth. Stores OperationRecord + project state snapshot."""

from __future__ import annotations
from collections import deque
from typing import List, Optional

from .project import OperationRecord


class UndoStack:
    """Bounded undo stack. The capacity is configurable (default 100)."""

    def __init__(self, capacity: int = 100):
        self._stack: deque[OperationRecord] = deque()
        self.capacity = max(1, int(capacity))

    def set_capacity(self, capacity: int) -> None:
        self.capacity = max(1, int(capacity))
        while len(self._stack) > self.capacity:
            self._stack.popleft()

    def push(self, rec: OperationRecord) -> None:
        self._stack.append(rec)
        while len(self._stack) > self.capacity:
            self._stack.popleft()

    def pop(self) -> Optional[OperationRecord]:
        if not self._stack:
            return None
        return self._stack.pop()

    def peek(self) -> Optional[OperationRecord]:
        if not self._stack:
            return None
        return self._stack[-1]

    def clear(self) -> None:
        self._stack.clear()

    def __len__(self) -> int:
        return len(self._stack)

    def __bool__(self) -> bool:
        return bool(self._stack)
