"""Tracing backends.

Two backends feed the same ExecutionRecorder:

* ``monitoring`` (Python 3.12+, default): uses ``sys.monitoring`` (PEP 669). Functions
  outside the traced root are switched off *per code object* the first time they run
  (``sys.monitoring.DISABLE``), so library and stdlib code costs almost nothing after
  its first call. No per-line events are ever generated. Generators and coroutines are
  handled precisely (resume vs. new call), and every thread is traced.
* ``settrace`` (fallback for 3.10/3.11): uses ``sys.settrace``. Filtered frames get no
  local tracer and traced frames have line events switched off, which removes most of
  the classic settrace overhead.
"""

from __future__ import annotations

import sys
import threading
import time
import types
from typing import TYPE_CHECKING

from callgraph.events import EventType, TraceEvent
from callgraph.filters import TraceFilter
from callgraph.model import FunctionIdentity
from callgraph.recorder import SAMPLE_CAP, AggregateRecorder, CCTNode, ExecutionRecorder, record_sample

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

HAS_MONITORING = hasattr(sys, "monitoring")
BACKENDS = ("auto", "monitoring", "settrace", "none")

_clock = time.perf_counter_ns


def identity_from_code(code: types.CodeType, module_name: str) -> FunctionIdentity:
    qualname = getattr(code, "co_qualname", None) or code.co_name
    qualified_name = f"{module_name}.{qualname}" if module_name else qualname
    return FunctionIdentity(
        name=code.co_name,
        qualified_name=qualified_name,
        filename=code.co_filename,
        lineno=code.co_firstlineno,
        module=module_name,
    )


def identity_from_frame(frame: types.FrameType) -> FunctionIdentity:
    return identity_from_code(frame.f_code, frame.f_globals.get("__name__", ""))


def resolve_backend(backend: str) -> str:
    if backend == "auto":
        return "monitoring" if HAS_MONITORING else "settrace"
    if backend == "monitoring" and not HAS_MONITORING:
        raise RuntimeError("the 'monitoring' backend requires Python 3.12+")
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend: {backend}")
    return backend


# --------------------------------------------------------------------------- settrace


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
        self._identities: dict[types.CodeType, FunctionIdentity | None] = {}

    def _identity(self, frame: types.FrameType) -> FunctionIdentity | None:
        code = frame.f_code
        try:
            return self._identities[code]
        except KeyError:
            identity = None
            if self.trace_filter.should_trace(code.co_filename):
                identity = identity_from_frame(frame)
            self._identities[code] = identity
            return identity

    def trace(self, frame: types.FrameType, event: str, arg: object) -> Callable[..., object] | None:
        """Global trace function: only ever sees 'call' events."""
        if event != "call":
            return None
        identity = self._identity(frame)
        if identity is None:
            return None  # no local tracer -> no line/return events for this frame
        frame.f_trace_lines = False
        now = _clock()
        tid = threading.get_ident()
        self.recorder.on_call(identity, now, tid)
        if self.event_sink is not None:
            caller = identity_from_frame(frame.f_back) if frame.f_back is not None else None
            self.event_sink(TraceEvent(EventType.CALL, identity, caller, now, tid))
        return self._local

    def _local(self, frame: types.FrameType, event: str, arg: object) -> Callable[..., object] | None:
        if event == "return":
            now = _clock()
            tid = threading.get_ident()
            self.recorder.on_return(now, tid)
            if self.event_sink is not None:
                identity = self._identities.get(frame.f_code)
                if identity is not None:
                    self.event_sink(TraceEvent(EventType.RETURN, identity, None, now, tid))
        return self._local

    def start(self) -> None:
        self._previous = sys.gettrace()
        threading.settrace(self.trace)
        sys.settrace(self.trace)

    def stop(self) -> None:
        sys.settrace(self._previous)
        threading.settrace(None)  # type: ignore[arg-type]


# ------------------------------------------------------------------------- monitoring


class MonitoringTracer:
    """sys.monitoring (PEP 669) backend.

    Performance notes (these callbacks run twice per traced call):
    * lookups are keyed by ``id(code)``: hashing a code object is expensive in CPython
      (it re-hashes bytecode and constants every time), an int hash is free. The code
      objects are kept alive in ``_codes`` so ids cannot be reused while tracing;
    * calling-context children are keyed by the same int for the same reason;
    * code outside the traced root returns ``DISABLE`` and is never seen again.
    """

    TOOL_NAME = "callgraph"

    def __init__(
        self,
        recorder: ExecutionRecorder | AggregateRecorder,
        trace_filter: TraceFilter,
        event_sink: Callable[[TraceEvent], None] | None = None,
    ) -> None:
        self.recorder = recorder
        self.trace_filter = trace_filter
        self.event_sink = event_sink
        # id(code) -> FunctionIdentity, or None when the code is filtered out
        self._identities: dict[int, FunctionIdentity | None] = {}
        self._codes: list[types.CodeType] = []
        self._tool_id: int | None = None

    def _identity(self, code: types.CodeType) -> FunctionIdentity | None:
        key = id(code)
        if key in self._identities:
            return self._identities[key]
        identity = None
        if self.trace_filter.should_trace(code.co_filename):
            frame = sys._getframe(1)
            while frame is not None and frame.f_code is not code:
                frame = frame.f_back
            module = frame.f_globals.get("__name__", "") if frame is not None else ""
            identity = identity_from_code(code, module)
        self._codes.append(code)
        self._identities[key] = identity
        return identity

    def _make_callbacks(self) -> tuple[Callable[..., object], ...]:
        """Generic callbacks: forward to recorder.on_call / on_return (and the event sink)."""
        ids = self._identities
        resolve = self._identity
        on_call = self.recorder.on_call
        on_return = self.recorder.on_return
        clock = _clock
        get_ident = threading.get_ident
        DISABLE = sys.monitoring.DISABLE
        sink = self.event_sink
        CALL, RETURN = EventType.CALL, EventType.RETURN

        def enter(code: types.CodeType, resumed: bool) -> object:
            key = id(code)
            identity = ids[key] if key in ids else resolve(code)
            if identity is None:
                return DISABLE
            now = clock()
            tid = get_ident()
            on_call(identity, now, tid, resumed)
            if sink is not None:
                sink(TraceEvent(CALL, identity, None, now, tid, resumed))
            return None

        def leave(code: types.CodeType, raised: bool) -> object:
            identity = ids.get(id(code))
            if identity is None:
                return DISABLE
            now = clock()
            tid = get_ident()
            on_return(now, tid, raised)
            if sink is not None:
                sink(TraceEvent(RETURN, identity, None, now, tid, False, raised))
            return None

        def on_start(code: types.CodeType, offset: int) -> object:
            return enter(code, False)

        def on_resume(code: types.CodeType, offset: int) -> object:
            return enter(code, True)

        def on_throw(code: types.CodeType, offset: int, exc: BaseException) -> None:
            # Not a local event: must not return DISABLE.
            key = id(code)
            if (ids[key] if key in ids else resolve(code)) is not None:
                enter(code, True)

        def on_exit(code: types.CodeType, offset: int, retval: object) -> object:
            return leave(code, False)

        def on_unwind(code: types.CodeType, offset: int, exc: BaseException) -> None:
            # PY_UNWIND is a global event and cannot be disabled: keep this cheap.
            if ids.get(id(code)) is not None:
                leave(code, True)

        return on_start, on_resume, on_throw, on_exit, on_unwind

    def _make_aggregate_callbacks(self, rec: AggregateRecorder) -> tuple[Callable[..., object], ...]:
        """Hot path for the default stats/html mode.

        The AggregateRecorder bookkeeping is inlined (one Python call per event instead
        of two), and the clock is read as late as possible on entry and as early as
        possible on exit so the tracer's own work is mostly excluded from durations.
        """
        ids = self._identities
        resolve = self._identity
        stacks = rec._stacks
        root = rec.root
        clock = _clock
        get_ident = threading.get_ident
        DISABLE = sys.monitoring.DISABLE
        CAP2 = 2 * SAMPLE_CAP
        Node = CCTNode
        # Single-threaded programs (the common case) skip the per-thread dict.
        main_tid = threading.get_ident()
        main_stack: list[list] = stacks.setdefault(main_tid, [])
        # Per-call overhead correction for duration samples (calibrated before the run):
        # a call with D descendant calls carries inner + D * (outer + inner) ns of tracer.
        outer_ns, inner_ns = rec.sample_correction
        per_desc = outer_ns + inner_ns
        counter = rec._counter  # one-element list: total calls started so far

        def enter(code: types.CodeType, resumed: bool) -> object:
            key = id(code)
            identity = ids[key] if key in ids else resolve(code)
            if identity is None:
                return DISABLE
            tid = get_ident()
            if tid == main_tid:
                stack = main_stack
            else:
                stack = stacks.get(tid)
                if stack is None:
                    stack = stacks[tid] = []
            children = stack[-1][0].children if stack else root.children
            node = children.get(key)
            if node is None:
                node = children[key] = Node(identity)
            if not resumed:
                node.calls += 1
            counter[0] += 1
            stack.append([node, clock(), 0, resumed, counter[0]])
            return None

        def leave(now: int, raised: bool) -> None:
            tid = get_ident()
            stack = main_stack if tid == main_tid else stacks.get(tid)
            if not stack:
                return
            node, start, child_ns, resumed, mark = stack.pop()
            duration = now - start
            node.total_ns += duration
            node.self_ns += duration - child_ns
            if stack:
                stack[-1][2] += duration
            if raised:
                node.raised += 1
            if not resumed:
                sample = duration - inner_ns - (counter[0] - mark) * per_desc
                sample = sample if sample > 0 else 0
                samples = node.samples
                if node.stride == 1 and len(samples) < CAP2 - 1:
                    samples.append(sample)
                else:
                    record_sample(node, sample)

        def on_start(code: types.CodeType, offset: int) -> object:
            # Inlined copy of enter(code, False): this is the hottest function.
            key = id(code)
            identity = ids[key] if key in ids else resolve(code)
            if identity is None:
                return DISABLE
            tid = get_ident()
            if tid == main_tid:
                stack = main_stack
            else:
                stack = stacks.get(tid)
                if stack is None:
                    stack = stacks[tid] = []
            children = stack[-1][0].children if stack else root.children
            node = children.get(key)
            if node is None:
                node = children[key] = Node(identity)
            node.calls += 1
            counter[0] += 1
            stack.append([node, clock(), 0, False, counter[0]])
            return None

        def on_resume(code: types.CodeType, offset: int) -> object:
            return enter(code, True)

        def on_throw(code: types.CodeType, offset: int, exc: BaseException) -> None:
            key = id(code)
            if (ids[key] if key in ids else resolve(code)) is not None:
                enter(code, True)

        def on_exit(code: types.CodeType, offset: int, retval: object) -> object:
            # Inlined copy of leave(now, False).
            now = clock()
            if ids.get(id(code)) is None:
                return DISABLE
            tid = get_ident()
            stack = main_stack if tid == main_tid else stacks.get(tid)
            if not stack:
                return None
            entry = stack.pop()
            node = entry[0]
            duration = now - entry[1]
            node.total_ns += duration
            node.self_ns += duration - entry[2]
            if stack:
                stack[-1][2] += duration
            if not entry[3]:
                sample = duration - inner_ns - (counter[0] - entry[4]) * per_desc
                sample = sample if sample > 0 else 0
                samples = node.samples
                if node.stride == 1 and len(samples) < CAP2 - 1:
                    samples.append(sample)
                else:
                    record_sample(node, sample)
            return None

        def on_unwind(code: types.CodeType, offset: int, exc: BaseException) -> None:
            now = clock()
            if ids.get(id(code)) is not None:
                leave(now, True)

        return on_start, on_resume, on_throw, on_exit, on_unwind

    def start(self) -> None:
        mon = sys.monitoring
        for tool_id in (mon.PROFILER_ID, 3, 4, 1):
            if mon.get_tool(tool_id) is None:
                mon.use_tool_id(tool_id, self.TOOL_NAME)
                self._tool_id = tool_id
                break
        else:
            raise RuntimeError("no free sys.monitoring tool id")
        tool, events = self._tool_id, mon.events
        if isinstance(self.recorder, AggregateRecorder) and self.event_sink is None:
            callbacks = self._make_aggregate_callbacks(self.recorder)
        else:
            callbacks = self._make_callbacks()
        on_start, on_resume, on_throw, on_exit, on_unwind = callbacks
        mon.register_callback(tool, events.PY_START, on_start)
        mon.register_callback(tool, events.PY_RESUME, on_resume)
        mon.register_callback(tool, events.PY_THROW, on_throw)
        mon.register_callback(tool, events.PY_RETURN, on_exit)
        mon.register_callback(tool, events.PY_YIELD, on_exit)
        mon.register_callback(tool, events.PY_UNWIND, on_unwind)
        mon.restart_events()  # clear DISABLEs left over from a previous trace
        mon.set_events(
            tool,
            events.PY_START | events.PY_RESUME | events.PY_THROW
            | events.PY_RETURN | events.PY_YIELD | events.PY_UNWIND,
        )

    def stop(self) -> None:
        if self._tool_id is None:
            return
        mon = sys.monitoring
        mon.set_events(self._tool_id, 0)
        for event in (mon.events.PY_START, mon.events.PY_RESUME, mon.events.PY_THROW,
                      mon.events.PY_RETURN, mon.events.PY_YIELD, mon.events.PY_UNWIND):
            mon.register_callback(self._tool_id, event, None)
        mon.free_tool_id(self._tool_id)
        self._tool_id = None


class _NullTracer:
    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def make_tracer(
    backend: str,
    recorder: ExecutionRecorder,
    trace_filter: TraceFilter,
    event_sink: Callable[[TraceEvent], None] | None = None,
) -> Tracer | MonitoringTracer | _NullTracer:
    backend = resolve_backend(backend)
    if backend == "monitoring":
        return MonitoringTracer(recorder, trace_filter, event_sink)
    if backend == "settrace":
        return Tracer(recorder, trace_filter, event_sink)
    return _NullTracer()


# ------------------------------------------------------------------------- run helpers


def run_traced(
    target: Callable[[], object],
    trace_filter: TraceFilter,
    event_sink: Callable[[TraceEvent], None] | None = None,
    backend: str = "auto",
) -> tuple[ExecutionRecorder, object | None]:
    recorder = ExecutionRecorder()
    tracer = make_tracer(backend, recorder, trace_filter, event_sink)
    tracer.start()
    result: object | None = None
    try:
        result = target()
    finally:
        tracer.stop()
        recorder.close_open_frames(_clock())
    return recorder, result


def run_script(
    script_path: Path,
    script_args: list[str] | None = None,
    trace_filter: TraceFilter | None = None,
    event_sink: Callable[[TraceEvent], None] | None = None,
    backend: str = "auto",
    recorder: ExecutionRecorder | AggregateRecorder | None = None,
) -> ExecutionRecorder | AggregateRecorder:
    script_path = script_path.resolve()
    if trace_filter is None:
        trace_filter = TraceFilter.for_script(script_path)

    with open(script_path, encoding="utf-8") as handle:
        code = compile(handle.read(), str(script_path), "exec")
    globals_dict: dict[str, object] = {
        "__name__": "__main__",
        "__file__": str(script_path),
        "__doc__": None,
        "__package__": None,
        "__spec__": None,
    }

    saved_argv = sys.argv
    sys.argv = [str(script_path), *(script_args or [])]
    # Behave like `python script.py`: the script's directory is importable.
    sys.path.insert(0, str(script_path.parent))

    if recorder is None:
        recorder = ExecutionRecorder()
    recorder.backend = resolve_backend(backend)
    tracer = make_tracer(backend, recorder, trace_filter, event_sink)
    tracer.start()
    try:
        exec(code, globals_dict)
    except SystemExit:
        pass
    finally:
        tracer.stop()
        recorder.close_open_frames(_clock())
        if isinstance(recorder, AggregateRecorder):
            recorder.count_events()
        sys.argv = saved_argv
        if sys.path and sys.path[0] == str(script_path.parent):
            sys.path.pop(0)
    return recorder
