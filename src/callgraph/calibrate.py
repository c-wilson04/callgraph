"""Instrumentation-overhead calibration.

Every traced call costs the tracer some time *between* the caller's clock reads but
*outside* the callee's own measured window. Left alone, that cost is billed to the
caller's self time, so a function that calls a tiny helper 100,000 times looks far
slower than it is. Like cProfile's bias calibration, we measure that per-call cost
once on a known workload and subtract it from the recorded totals.
"""

from __future__ import annotations

import time
from pathlib import Path

from callgraph.filters import TraceFilter
from callgraph.recorder import AggregateRecorder, CCTNode

_SOURCE = """
def _cg_child():
    pass

def _cg_parent(n):
    for _ in range(n):
        _cg_child()
"""

_N = 20_000


def calibrate(backend: str, root: Path | None = None) -> tuple[int, int]:
    """Estimate tracer overhead per traced call, in ns, as ``(outer, inner)``.

    * outer: time billed to the *caller* (between its clock reads, outside the callee);
    * inner: time inside the callee's own measured window that is really the tracer.
    """
    from callgraph.instrumentation import make_tracer, resolve_backend

    backend = resolve_backend(backend)
    if backend == "none":
        return 0, 0
    root = (root or Path.cwd()).resolve()
    # A synthetic filename under the root, so the default filter traces it.
    code = compile(_SOURCE, str(root / "__callgraph_calibration__.py"), "exec")
    namespace: dict[str, object] = {"__name__": "__callgraph_calibration__"}
    exec(code, namespace)
    parent = namespace["_cg_parent"]

    best_untraced = min(_timed(parent) for _ in range(3))
    estimates, inner = [], []
    for _ in range(3):
        recorder = AggregateRecorder()
        tracer = make_tracer(backend, recorder, TraceFilter(root=root))
        tracer.start()
        try:
            parent(_N)  # type: ignore[operator]
        finally:
            tracer.stop()
        node = _find(recorder.root, "_cg_parent")
        child = _find(recorder.root, "_cg_child")
        if node is not None and child is not None and child.calls:
            # The empty child's measured time is (almost) all tracer.
            inner_ns = child.total_ns / child.calls
            inner.append(inner_ns)
            estimates.append((node.self_ns - best_untraced) / _N)
    if not estimates:
        return 0, 0
    return max(0, int(min(estimates))), max(0, int(min(inner)))


def _timed(fn: object) -> int:
    start = time.perf_counter_ns()
    fn(_N)  # type: ignore[operator]
    return time.perf_counter_ns() - start


def _find(root: CCTNode, name: str) -> CCTNode | None:
    todo = list(root.children.values())
    while todo:
        node = todo.pop()
        if node.identity is not None and node.identity.name == name:
            return node
        todo.extend(node.children.values())
    return None


def apply_overhead_correction(recorder: AggregateRecorder, overhead: tuple[int, int]) -> None:
    """Remove calibrated tracer overhead from every node's measured times.

    For a node with ``calls`` calls, ``direct`` child calls and ``below`` descendant
    calls, what we measured is:

        self  = true_self  + calls * inner + direct * outer
        total = true_total + calls * inner + below * (outer + inner)
    """
    outer, inner = overhead
    if outer <= 0 and inner <= 0:
        return
    recorder.overhead_ns = outer + inner
    order: list[CCTNode] = []
    todo = list(recorder.root.children.values())
    while todo:
        node = todo.pop()
        order.append(node)
        todo.extend(node.children.values())
    descendants: dict[int, int] = {}
    for node in reversed(order):
        direct = sum(child.calls for child in node.children.values())
        below = direct + sum(descendants[id(child)] for child in node.children.values())
        descendants[id(node)] = below
        node.self_ns = max(0, node.self_ns - node.calls * inner - direct * outer)
        node.total_ns = max(node.self_ns, node.total_ns - node.calls * inner - below * (outer + inner))
        # Duration samples were already corrected per call, during tracing.
