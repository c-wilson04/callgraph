from __future__ import annotations

from typing import TYPE_CHECKING

from callgraph.events import EventType, TraceEvent
from callgraph.model import CallTreeNode

if TYPE_CHECKING:
    from collections.abc import Iterable


class ExecutionRecorder:
    """Builds a call tree from CALL/RETURN events using a stack."""

    def __init__(self) -> None:
        self._stack: list[CallTreeNode] = []
        self._root: CallTreeNode | None = None
        self._event_count = 0

    @property
    def event_count(self) -> int:
        return self._event_count

    def handle(self, event: TraceEvent) -> None:
        self._event_count += 1
        if event.event_type is EventType.CALL:
            self._handle_call(event)
        else:
            self._handle_return()

    def _handle_call(self, event: TraceEvent) -> None:
        node = CallTreeNode(identity=event.identity)
        if self._stack:
            self._stack[-1].children.append(node)
        else:
            self._root = node
        self._stack.append(node)

    def _handle_return(self) -> None:
        if self._stack:
            self._stack.pop()

    def finalize(self) -> CallTreeNode | None:
        return self._root

    def feed(self, events: Iterable[TraceEvent]) -> CallTreeNode | None:
        for event in events:
            self.handle(event)
        return self.finalize()
