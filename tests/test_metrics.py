import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from callgraph.api import build_call_tree, trace
from callgraph.calibrate import apply_overhead_correction, calibrate
from callgraph.cli import _split_argv
from callgraph.events import EventType, TraceEvent
from callgraph.filters import TraceFilter
from callgraph.instrumentation import HAS_MONITORING, run_script
from callgraph.metrics import compute_metrics
from callgraph.model import FunctionIdentity
from callgraph.recorder import SAMPLE_CAP, AggregateRecorder, CCTNode, ExecutionRecorder, record_sample
from callgraph.render.ascii import render_ascii
from callgraph.render.html import render_html

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
BACKENDS = ["settrace"] + (["monitoring"] if HAS_MONITORING else [])


def _write(tmp_path: Path, name: str, source: str) -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def _metrics(script: Path, backend: str, **kwargs) -> dict:
    rec = run_script(script, trace_filter=TraceFilter.for_script(script), backend=backend,
                     recorder=AggregateRecorder())
    return compute_metrics(rec, include_source=False, **kwargs)


def _by_name(metrics: dict) -> dict:
    return {f["name"]: f for f in metrics["functions"].values()}


# ------------------------------------------------------------------- counting / tree


@pytest.mark.parametrize("backend", BACKENDS)
def test_call_counts_and_edges(tmp_path, backend):
    script = _write(tmp_path, "loop.py", (
        "def leaf(i):\n    return i * 2\n\n"
        "def mid(n):\n    return sum(leaf(i) for i in range(n))\n\n"
        "def top():\n    for _ in range(10):\n        mid(5)\n\n"
        "top()\n"
    ))
    m = _metrics(script, backend)
    f = _by_name(m)
    assert f["top"]["calls"] == 1
    assert f["mid"]["calls"] == 10
    assert f["leaf"]["calls"] == 50
    edges = {(m["functions"][e["source"]]["name"], m["functions"][e["target"]]["name"]): e["calls"]
             for e in m["edges"]}
    assert edges[("top", "mid")] == 10
    assert edges[("<genexpr>", "leaf")] == 50
    assert m["hot_paths"][0]["calls"] == 50


@pytest.mark.parametrize("backend", BACKENDS)
def test_recursion_is_not_double_counted(tmp_path, backend):
    script = _write(tmp_path, "rec.py", (
        "import time\n"
        "def fact(n):\n"
        "    if n <= 1:\n        time.sleep(0.002)\n        return 1\n"
        "    return n * fact(n - 1)\n\n"
        "fact(6)\n"
    ))
    f = _by_name(_metrics(script, backend))["fact"]
    assert f["calls"] == 6
    # Inclusive time must be roughly one sleep, not 6 nested copies of it.
    assert 1_500_000 < f["total_ns"] < 6_000_000


@pytest.mark.skipif(not HAS_MONITORING, reason="precise generator handling needs sys.monitoring")
def test_generator_resumes_are_not_counted_as_calls(tmp_path):
    script = _write(tmp_path, "gen.py", (
        "def numbers():\n    for i in range(25):\n        yield i\n\n"
        "def consume():\n    return sum(numbers())\n\n"
        "consume()\n"
    ))
    f = _by_name(_metrics(script, "monitoring"))
    assert f["numbers"]["calls"] == 1
    assert f["consume"]["calls"] == 1


@pytest.mark.parametrize("backend", BACKENDS)
def test_exceptions_are_recorded_and_stack_stays_balanced(tmp_path, backend):
    script = _write(tmp_path, "exc.py", (
        "def bad():\n    raise ValueError('x')\n\n"
        "def guarded():\n    try:\n        bad()\n    except ValueError:\n        pass\n    after()\n\n"
        "def after():\n    return 1\n\n"
        "for _ in range(3):\n    guarded()\n"
    ))
    m = _metrics(script, backend)
    f = _by_name(m)
    assert f["bad"]["calls"] == 3
    assert f["after"]["calls"] == 3
    if backend == "monitoring":
        assert f["bad"]["raised"] == 3
    edges = {(m["functions"][e["source"]]["name"], m["functions"][e["target"]]["name"]) for e in m["edges"]}
    # `after` must be attributed to `guarded`, not to the function that raised.
    assert ("guarded", "after") in edges
    assert ("bad", "after") not in edges


@pytest.mark.skipif(not HAS_MONITORING, reason="multi-thread tracing uses sys.monitoring")
def test_threads_are_traced(tmp_path):
    script = _write(tmp_path, "threads.py", (
        "import threading\n"
        "def work():\n    return sum(range(100))\n\n"
        "def worker():\n    for _ in range(4):\n        work()\n\n"
        "ts = [threading.Thread(target=worker) for _ in range(3)]\n"
        "for t in ts: t.start()\n"
        "for t in ts: t.join()\n"
    ))
    f = _by_name(_metrics(script, "monitoring"))
    assert f["worker"]["calls"] == 3
    assert f["work"]["calls"] == 12


def test_stdlib_and_tracer_are_filtered(tmp_path):
    script = _write(tmp_path, "std.py", "import json\n\ndef main():\n    json.dumps({'a': 1})\n\nmain()\n")
    names = set(_by_name(_metrics(script, "auto")))
    assert "main" in names
    assert "dumps" not in names and "encode" not in names
    assert not any(n.startswith("_cg_") for n in names)


def test_trace_context_manager(tmp_path):
    def inner():
        return 1

    def outer():
        return inner() + inner()

    with trace(root=Path(__file__).parent) as recorder:
        outer()
    tree = build_call_tree(recorder)
    assert tree.root is not None
    names = {f["name"]: f["calls"] for f in compute_metrics(tree, include_source=False)["functions"].values()}
    assert names["inner"] == 2


# ------------------------------------------------------------------- recorder internals


def _ident(name: str) -> FunctionIdentity:
    return FunctionIdentity(name, f"m.{name}", "/m.py", 1, "m")


def test_full_tree_and_aggregate_agree():
    a, b, c = _ident("a"), _ident("b"), _ident("c")
    events = []
    t = 0
    for ident, kind in [(a, EventType.CALL), (b, EventType.CALL), (b, EventType.RETURN),
                        (b, EventType.CALL), (c, EventType.CALL), (c, EventType.RETURN),
                        (b, EventType.RETURN), (a, EventType.RETURN)]:
        t += 100
        events.append(TraceEvent(kind, ident, None, t))
    full = ExecutionRecorder()
    full.feed(events)
    agg = AggregateRecorder()
    for e in events:
        agg.handle(e)
    m1 = compute_metrics(build_call_tree(full), include_source=False)
    m2 = compute_metrics(agg, include_source=False)
    strip = lambda m: {k: {x: v[x] for x in ("calls", "total_ns", "self_ns")} for k, v in m["functions"].items()}
    assert strip(m1) == strip(m2)
    assert _by_name(m1)["b"]["calls"] == 2


def test_samples_stay_bounded_and_representative():
    node = CCTNode(_ident("hot"))
    n = SAMPLE_CAP * 40
    for i in range(n):
        record_sample(node, i % 1000)
    assert len(node.samples) <= 2 * SAMPLE_CAP
    assert node.stride > 1
    assert 400 <= sorted(node.samples)[len(node.samples) // 2] <= 600


def test_overhead_correction_never_goes_negative():
    agg = AggregateRecorder()
    a, b = _ident("a"), _ident("b")
    agg.on_call(a, 0)
    for i in range(100):
        agg.on_call(b, 10 + i * 10)
        agg.on_return(15 + i * 10)
    agg.on_return(2000)
    apply_overhead_correction(agg, (50, 50))
    for node in [agg.root.children[a], *agg.root.children[a].children.values()]:
        assert node.self_ns >= 0 and node.total_ns >= node.self_ns


@pytest.mark.parametrize("backend", BACKENDS)
def test_calibration_returns_sane_values(backend):
    outer, inner = calibrate(backend, ROOT)
    assert 0 <= outer < 50_000
    assert 0 <= inner < 50_000


# ------------------------------------------------------------------- renderers / CLI


def test_ascii_merges_repeated_calls(tmp_path):
    script = _write(tmp_path, "rep.py", "def f():\n    pass\n\ndef g():\n    for _ in range(3):\n        f()\n\ng()\n")
    rec = run_script(script, recorder=AggregateRecorder())
    assert render_ascii(rec) == "g\n└── f ×3"


def test_html_dashboard_is_self_contained(tmp_path):
    script = EXAMPLES / "abc_demo.py"
    rec = run_script(script, recorder=AggregateRecorder())
    page = render_html(compute_metrics(rec, script="abc_demo.py"))
    assert "/*__CALLGRAPH_DATA__*/" not in page
    assert "<script src" not in page and "<link" not in page  # works offline
    data = page.split("const DATA = ", 1)[1].split(";\n", 1)[0]
    assert json.loads(data)["summary"]["total_calls"] == 5  # <module>, a, b, c, d


def test_split_argv_accepts_flags_after_script():
    ours, theirs = _split_argv(["run", "app.py", "--format", "json", "100", "--", "--format", "x"])
    assert ours == ["run", "app.py", "--format", "json"]
    assert theirs == ["100", "--format", "x"]
    ours, theirs = _split_argv(["run", "--format=html", "app.py", "--no-latency"])
    assert ours == ["run", "--format=html", "app.py"]
    assert theirs == ["--no-latency"]


def _cli(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run([sys.executable, "-m", "callgraph", *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", env=env, check=True)


def test_cli_stats_and_html(tmp_path):
    result = _cli("run", "examples/abc_demo.py", "--format", "stats")
    assert "Most called functions" in result.stdout
    out = tmp_path / "dash.html"
    _cli("run", "--format", "html", "-o", str(out), "examples/abc_demo.py")
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_cli_json_after_script_path():
    result = _cli("run", "examples/abc_demo.py", "--format", "json")
    assert json.loads(result.stdout)["root"] is not None


def test_bookstore_example_runs_under_tracing():
    script = EXAMPLES / "bookstore" / "app.py"
    rec = run_script(script, script_args=["40", "--no-latency"], recorder=AggregateRecorder())
    f = _by_name(compute_metrics(rec, include_source=False))
    assert f["dispatch"]["calls"] == 40
    assert f["normalize"]["calls"] > 1000
