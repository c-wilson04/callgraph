from __future__ import annotations

import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

from callgraph.filters import TraceFilter
from callgraph.instrumentation import make_tracer, resolve_backend
from callgraph.model import CallTree
from callgraph.recorder import ExecutionRecorder

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@contextmanager
def trace(
    root: Path | None = None,
    include_site_packages: bool = False,
    exclude_patterns: list[str] | None = None,
    backend: str = "auto",
) -> Iterator[ExecutionRecorder]:
    """Context manager that traces code executed within the block."""
    trace_filter = TraceFilter(
        root=root,
        include_site_packages=include_site_packages,
        exclude_patterns=exclude_patterns or [],
    )
    recorder = ExecutionRecorder()
    recorder.backend = resolve_backend(backend)
    tracer = make_tracer(backend, recorder, trace_filter)
    tracer.start()
    try:
        yield recorder
    finally:
        tracer.stop()
        recorder.close_open_frames(time.perf_counter_ns())


def build_call_tree(
    recorder: ExecutionRecorder,
    run_id: str = "1",
    wall_ns: int = 0,
    backend: str | None = None,
) -> CallTree:
    root = recorder.finalize()
    return CallTree(
        run_id=run_id,
        root=root,
        event_count=recorder.event_count,
        wall_ns=wall_ns or (root.duration_ns if root else 0),
        backend=backend or getattr(recorder, "backend", ""),
    )
