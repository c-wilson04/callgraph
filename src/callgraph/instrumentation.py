from __future__ import annotations

import sys
import types
from typing import TYPE_CHECKING

from callgraph.events import EventType, TraceEvent
from callgraph.filters import TraceFilter
from callgraph.model import FunctionIdentity
from callgraph.recorder import ExecutionRecorder

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def identity_from_frame(frame: types.FrameType) -> FunctionIdentity:
    code = frame.f_code
    module_name = frame.f_globals.get("__name__", "")
    qualname = code.co_qualname or code.co_name
    if module_name and qualname:
        qualified_name = f"{module_name}.{qualname}"
    else:
        qualified_name = qualname or code.co_name
    return FunctionIdentity(
        name=code.co_name,
        qualified_name=qualified_name,
        filename=code.co_filename,
        lineno=frame.f_lineno,
    )


class Tracer:
    """sys.settrace hook that emits CALL/RETURN events into a recorder."""

    def __init__(
        self,
        recorder: ExecutionRecorder,
        trace_filter: TraceFilter,
        event_sink: Callable[[TraceEvent], None] | None = None,
    ) -> None:
        self.recorder = recorder
        self.trace_filter = trace_filter
        self.event_sink = event_sink
        self._trace_stack: list[FunctionIdentity] = []
        self._skipped_depth = 0

    def trace(self, frame: types.FrameType, event: str, arg: object) -> Callable[..., object]:
        if event == "line":
            return self.trace
        if event not in ("call", "return"):
            return self.trace

        identity = identity_from_frame(frame)
        if not self.trace_filter.should_trace(identity.filename):
            if event == "call":
                self._skipped_depth += 1
            elif event == "return" and self._skipped_depth > 0:
                self._skipped_depth -= 1
            return self.trace

        if event == "call":
            caller = identity_from_frame(frame.f_back) if frame.f_back is not None else None
            trace_event = TraceEvent(
                event_type=EventType.CALL,
                identity=identity,
                caller=caller,
            )
            self._trace_stack.append(identity)
            self.recorder.handle(trace_event)
            if self.event_sink is not None:
                self.event_sink(trace_event)
        else:
            if not self._trace_stack:
                return self.trace
            popped = self._trace_stack.pop()
            trace_event = TraceEvent(
                event_type=EventType.RETURN,
                identity=popped,
                caller=None,
            )
            self.recorder.handle(trace_event)
            if self.event_sink is not None:
                self.event_sink(trace_event)

        return self.trace


def run_traced(
    target: Callable[[], object],
    trace_filter: TraceFilter,
    event_sink: Callable[[TraceEvent], None] | None = None,
) -> tuple[ExecutionRecorder, object | None]:
    recorder = ExecutionRecorder()
    tracer = Tracer(recorder, trace_filter, event_sink=event_sink)
    previous_trace = sys.gettrace()
    sys.settrace(tracer.trace)
    result: object | None = None
    try:
        result = target()
    except SystemExit:
        raise
    finally:
        sys.settrace(previous_trace)
    return recorder, result


def run_script(
    script_path: Path,
    script_args: list[str] | None = None,
    trace_filter: TraceFilter | None = None,
    event_sink: Callable[[TraceEvent], None] | None = None,
) -> ExecutionRecorder:
    script_path = script_path.resolve()
    if trace_filter is None:
        trace_filter = TraceFilter.for_script(script_path)

    script_args = script_args or []
    argv = [str(script_path), *script_args]

    def execute() -> None:
        sys.argv = argv
        with open(script_path, encoding="utf-8") as handle:
            code = compile(handle.read(), str(script_path), "exec")
        globals_dict: dict[str, object] = {
            "__name__": "__main__",
            "__file__": str(script_path),
            "__doc__": None,
            "__package__": None,
            "__spec__": None,
        }
        exec(code, globals_dict)

    recorder = ExecutionRecorder()
    tracer = Tracer(recorder, trace_filter, event_sink=event_sink)
    previous_trace = sys.gettrace()
    sys.settrace(tracer.trace)
    try:
        execute()
    except SystemExit:
        pass
    finally:
        sys.settrace(previous_trace)
    return recorder
