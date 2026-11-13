# Callgraph

**See what your Python code actually does at runtime.** Callgraph traces a real run and
shows which functions and paths executed, in what order, how often, and how long they
took. It works from the actual execution, not from what a static analyzer guesses might run.

```bash
callgraph run --format html --open app.py
```

You get one self-contained HTML dashboard (it works offline and you can attach it to a PR or ticket) with:

- **A runtime call graph.** A box is a function and an edge is a call that really happened, with
  call counts. Click any function to see its metrics, callers, callees and **source code**.
- **A replay of the execution** that animates the run through the graph in the order it happened.
- **An execution pipeline** (flame view) of every distinct call path, left to right in
  first-run order, with width proportional to time.
- **Rankings** by calls, total time, self time, mean, median and p95.
- **Hottest call paths**, the chains of functions that run most often or take the most time.

No code changes, decorators or agents are needed, and there are no dependencies.

## Install

```bash
pip install -e ".[dev]"      # Python 3.10+; 3.12+ recommended (low-overhead backend)
```

## Usage

```bash
callgraph run app.py                       # call tree in the terminal (repeats merged as ×N)
callgraph run app.py --format stats        # top functions, where time goes, hot paths
callgraph run app.py --format html --open  # interactive dashboard
callgraph bench app.py                     # measure tracing overhead on your workload
```

Callgraph flags can go before or after the script. Arguments it doesn't recognize are
passed to the script, and everything after `--` goes to the script untouched:

```bash
callgraph run app.py 1000 --format stats          # app.py receives "1000"
callgraph run app.py --format json -- --format x  # app.py receives "--format x"
```

| Format | Output |
|--------|--------|
| `ascii` (default) | Call tree, repeated paths merged as `name ×N` |
| `stats` | Terminal tables: most called, most time, hottest paths |
| `html` | Interactive dashboard (`-o file.html`, `--open`) |
| `metrics-json` | All metrics as JSON, for CI or your own tooling |
| `json` / `mermaid` / `events` | Full per-call tree / Mermaid diagram / raw event stream |

### Scoping and filtering

By default only code under the script's directory is traced, and the standard library
and site-packages are skipped. With the `sys.monitoring` backend, excluded code
**costs almost nothing**, because it is switched off per function the first time it runs.

```bash
callgraph run app.py --root src/                # what counts as "your code"
callgraph run app.py --exclude migrations/      # skip paths containing this (repeatable)
callgraph run app.py --include-site-packages    # also trace third-party libraries
```

### Try it on the sample app

`examples/bookstore/` is a small layered API (router → handlers → services → domain → data)
replaying 400 simulated requests with database round-trips:

```bash
callgraph run examples/bookstore/app.py --format html --open
```

Or run the guided demo: `demo/run-demo.ps1` (Windows) or `demo/run-demo.sh`.

### Programmatic API

```python
from callgraph import trace
from callgraph.metrics import compute_metrics
from callgraph.render.html import render_html

with trace() as recorder:
    main()

metrics = compute_metrics(recorder)               # dict: functions, edges, hot paths...
open("report.html", "w").write(render_html(metrics))
```

## How it works

```
your program ──► tracing backend ──► recorder ──► metrics ──► ascii / stats / html / json
                 sys.monitoring      calling-context tree    counts, times,
                 (or sys.settrace)   (merged per call path)  percentiles, hot paths
```

| Layer | Module | Responsibility |
|-------|--------|----------------|
| Backends | `instrumentation.py` | `sys.monitoring` (PEP 669, 3.12+) or `sys.settrace` fallback |
| Filtering | `filters.py` | Which files count as user code (cached per file) |
| Recorder | `recorder.py` | `AggregateRecorder`: calling-context tree built on the fly with bounded duration samples. `ExecutionRecorder`: full per-call tree |
| Calibration | `calibrate.py` | Measures the tracer's own per-call cost and subtracts it from timings |
| Metrics | `metrics.py` | Per-function stats, edges, hot paths, recursion-safe inclusive time |
| Render | `render/` | ASCII, stats, HTML dashboard, JSON, Mermaid, events |
| CLI | `cli.py` | `callgraph run`, `callgraph bench` |

**Accuracy.** Callgraph is a deterministic tracer: every call is counted exactly. Timings
include the tracer's own cost, so at startup callgraph measures that cost on a known
workload and subtracts it from every function, per call, based on how many calls happened
underneath (similar to cProfile's bias calibration). Use `--no-calibrate` to see raw numbers.

**Overhead.** Overhead scales with *how many* calls you trace, not with how long they take.
These are measured on the bookstore sample with `callgraph bench` (Windows, Python 3.13):

| Workload | sys.monitoring | settrace |
|----------|---------------:|---------:|
| API with DB round-trips, tracing scoped (`--exclude search.py`) | **1.11×** | 1.65× |
| API with DB round-trips, everything traced | 2.5× | 3.3× |
| Pure CPU worst case: a Python call every ~200 ns (`--no-latency`) | 8.9× | 12.6× |

For comparison, cProfile (written in C) measures 4.3× on the same worst case. Run
`callgraph bench your_script.py` to measure your own workload.

## Limitations

- **Python only** for now, and Python-level code only: time spent inside C extensions is
  attributed to the Python function that called them.
- **Async:** coroutine and generator suspensions are handled (a resume is not a new call),
  but the graph shows the synchronous call stack, not the task or await graph.
- **Threads** are traced with the `sys.monitoring` backend. With `settrace`, only threads
  started after tracing begins are traced.
- **Very hot tiny functions** (millions of calls) dominate overhead. Scope them out with `--exclude`.

## Development

```bash
pytest
```
