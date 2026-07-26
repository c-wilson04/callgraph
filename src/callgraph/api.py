from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from callgraph.filters import TraceFilter
from callgraph.instrumentation import Tracer
from callgraph.model import CallTree
from callgraph.recorder import ExecutionRecorder

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

import sys


@contextmanager
def trace(
    root: Path | None = None,
    include_site_packages: bool = False,
    exclude_patterns: list[str] | None = None,
) -> Iterator[ExecutionRecorder]:
    """Context manager that traces code executed within the block."""
    trace_filter = TraceFilter(
        root=root,
        include_site_packages=include_site_packages,
        exclude_patterns=exclude_patterns or [],
    )
    recorder = ExecutionRecorder()
    tracer = Tracer(recorder, trace_filter)
    previous_trace = sys.gettrace()
    sys.settrace(tracer.trace)
    try:
        yield recorder
    finally:
        sys.settrace(previous_trace)


def build_call_tree(
    recorder: ExecutionRecorder,
    run_id: str = "1",
) -> CallTree:
    root = recorder.finalize()
    return CallTree(run_id=run_id, root=root, event_count=recorder.event_count)
