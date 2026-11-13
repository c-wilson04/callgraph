from __future__ import annotations

from typing import TYPE_CHECKING

from callgraph.events import EventType, TraceEvent
from callgraph.model import CallTreeNode, FunctionIdentity  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Iterable

PROGRAM_IDENTITY = FunctionIdentity(
    name="<program>",
    qualified_name="<program>",
    filename="<program>",
    lineno=0,
)


class ExecutionRecorder:
    """Builds a call tree from CALL/RETURN events using one stack per thread."""

    def __init__(self) -> None:
        self._stacks: dict[int, list[CallTreeNode]] = {}
        self._roots: list[CallTreeNode] = []
        self._event_count = 0
        self.backend = ""

    @property
    def event_count(self) -> int:
        return self._event_count

    def handle(self, event: TraceEvent) -> None:
        if event.event_type is EventType.CALL:
            self.on_call(event.identity, event.timestamp_ns, event.thread_id, event.resumed)
        else:
            self.on_return(event.timestamp_ns, event.thread_id, event.raised)

    # Fast paths used directly by the tracing backends (no event object allocation).

    def on_call(
        self,
        identity: FunctionIdentity,
        timestamp_ns: int,
        thread_id: int = 0,
        resumed: bool = False,
    ) -> None:
        self._event_count += 1
        node = CallTreeNode(identity, [], timestamp_ns, timestamp_ns, resumed)
        stack = self._stacks.get(thread_id)
        if stack is None:
            stack = self._stacks[thread_id] = []
        if stack:
            stack[-1].children.append(node)
        else:
            self._roots.append(node)
        stack.append(node)

    def on_return(self, timestamp_ns: int, thread_id: int = 0, raised: bool = False) -> None:
        self._event_count += 1
        stack = self._stacks.get(thread_id)
        if not stack:
            return
        node = stack.pop()
        node.end_ns = timestamp_ns
        if raised:
            node.raised = True

    def close_open_frames(self, timestamp_ns: int) -> None:
        """Close frames still open when tracing stopped (e.g. sys.exit inside a call)."""
        for stack in self._stacks.values():
            while stack:
                node = stack.pop()
                if timestamp_ns:
                    node.end_ns = timestamp_ns

    def finalize(self) -> CallTreeNode | None:
        if not self._roots:
            return None
        if len(self._roots) == 1:
            return self._roots[0]
        start = min(root.start_ns for root in self._roots)
        end = max(root.end_ns for root in self._roots)
        return CallTreeNode(
            identity=PROGRAM_IDENTITY,
            children=list(self._roots),
            start_ns=start,
            end_ns=end,
        )

    def feed(self, events: Iterable[TraceEvent]) -> CallTreeNode | None:
        for event in events:
            self.handle(event)
        return self.finalize()


# --------------------------------------------------------------------------- aggregate


SAMPLE_CAP = 4_096


class CCTNode:
    """Calling-context tree node: all calls reaching ``identity`` via the same path.

    ``samples`` holds per-call durations, bounded: every sample is kept up to
    SAMPLE_CAP, then the list is decimated (every 2nd, 4th, ... call is kept) so memory
    stays bounded on hot paths while median / p95 stay representative.
    """

    __slots__ = ("identity", "children", "calls", "total_ns", "self_ns", "raised",
                 "samples", "stride", "skip")

    def __init__(self, identity: FunctionIdentity | None) -> None:
        self.identity = identity
        self.children: dict[FunctionIdentity, CCTNode] = {}
        self.calls = 0
        self.total_ns = 0
        self.self_ns = 0
        self.raised = 0
        self.samples: list[int] = []
        self.stride = 1
        self.skip = 0

    def add_sample(self, duration: int) -> None:
        """Slow path, called once the node has SAMPLE_CAP samples."""
        if self.skip == 0:
            self.samples.append(duration)
            if len(self.samples) >= 2 * SAMPLE_CAP:
                del self.samples[1::2]
                self.stride *= 2
        self.skip = (self.skip + 1) % self.stride


def record_sample(node: CCTNode, duration: int) -> None:
    if node.stride == 1 and len(node.samples) < 2 * SAMPLE_CAP:
        node.samples.append(duration)
        if len(node.samples) >= 2 * SAMPLE_CAP:
            del node.samples[1::2]
            node.stride = 2
    else:
        node.add_sample(duration)


class AggregateRecorder:
    """Low-overhead recorder: merges calls into a calling-context tree as they happen.

    Unlike ExecutionRecorder it allocates nothing per call (only per distinct call path),
    so memory stays bounded and the tracing hot path is short. Used for stats / html /
    ascii output; the full per-call tree (json / mermaid / events) needs ExecutionRecorder.
    """

    def __init__(self) -> None:
        self.root = CCTNode(None)
        self._stacks: dict[int, list[list]] = {}
        self._event_count = 0
        self.backend = ""
        self.overhead_ns = 0
        # (outer, inner) ns per call, set before tracing so each duration sample can be
        # corrected by its own descendant count (see callgraph.calibrate).
        self.sample_correction: tuple[int, int] = (0, 0)
        self._counter = [0]

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def durations(self) -> dict[FunctionIdentity, list[tuple[list[int], int]]]:
        """Per-function duration samples as (samples, weight) groups, one per call path.

        A path whose samples were decimated by stride N gets weight N, so quantiles
        computed over all groups weigh every path in proportion to its calls.
        """
        merged: dict[FunctionIdentity, list[tuple[list[int], int]]] = {}
        todo = list(self.root.children.values())
        while todo:
            node = todo.pop()
            if node.samples:
                merged.setdefault(node.identity, []).append((node.samples, node.stride))
            todo.extend(node.children.values())
        return merged

    def on_call(
        self,
        identity: FunctionIdentity,
        timestamp_ns: int,
        thread_id: int = 0,
        resumed: bool = False,
    ) -> None:
        stack = self._stacks.get(thread_id)
        if stack is None:
            stack = self._stacks[thread_id] = []
        parent = stack[-1][0] if stack else self.root
        node = parent.children.get(identity)
        if node is None:
            node = parent.children[identity] = CCTNode(identity)
        if not resumed:
            node.calls += 1
        self._counter[0] += 1
        stack.append([node, timestamp_ns, 0, resumed, self._counter[0]])

    def on_return(self, timestamp_ns: int, thread_id: int = 0, raised: bool = False) -> None:
        stack = self._stacks.get(thread_id)
        if not stack:
            return
        node, start, child_ns, resumed, mark = stack.pop()
        duration = timestamp_ns - start
        node.total_ns += duration
        node.self_ns += duration - child_ns
        if stack:
            stack[-1][2] += duration
        if raised:
            node.raised += 1
        if not resumed:
            outer, inner = self.sample_correction
            sample = duration - inner - (self._counter[0] - mark) * (outer + inner)
            record_sample(node, sample if sample > 0 else 0)

    def handle(self, event: TraceEvent) -> None:
        if event.event_type is EventType.CALL:
            self.on_call(event.identity, event.timestamp_ns, event.thread_id, event.resumed)
        else:
            self.on_return(event.timestamp_ns, event.thread_id, event.raised)

    def close_open_frames(self, timestamp_ns: int) -> None:
        for tid, stack in self._stacks.items():
            while stack:
                self.on_return(timestamp_ns, tid)

    def count_events(self) -> None:
        """Event count is derived (2 per call) to keep it off the hot path."""
        total = 0
        todo = [self.root]
        while todo:
            node = todo.pop()
            total += node.calls
            todo.extend(node.children.values())
        self._event_count = 2 * total
