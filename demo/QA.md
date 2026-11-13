# callgraph: Q&A cheat sheet

Short answers first, detail after the dash. Numbers come from `callgraph bench` on the
bookstore sample (Windows, Python 3.13). Re-run them on the presenting machine.

## Performance / overhead (expect this one first)

**"Does it slow down my runs?"**
Yes, all tracers do. It's small when scoped and honest when it isn't. Bookstore API with DB
round-trips: **1.11×** with tracing scoped (`--exclude search.py`), **2.5×** with
everything traced. The worst case (pure CPU, a Python call every ~200ns) is about 9×.
`callgraph bench your_script.py` measures it on *your* workload.

**"Why is the worst case so high?"**
Overhead scales with the *number of calls*, not their duration. Each traced call costs
about 1µs of Python callback work. A function that does 50ns of real work becomes about
20× slower, while one that waits 50ms on a database is unaffected. Real services are
mostly the second kind.

**"How does that compare to cProfile?"**
cProfile is written in C and measures 4.3× on the same worst case, against our 8.9×
there. But cProfile gives you a flat table, not paths, order, percentiles or a pipeline
view. Moving the hot loop to C or Rust is on the roadmap.

**"Why not just use sampling profilers (py-spy, Scalene)?"**
Sampling is cheaper, but it *estimates*. It can't tell you that `normalize` was called
exactly 652,402 times, or show the exact path and order. Use sampling to find hotspots in
production. Use callgraph to understand *behaviour*: paths, counts, order and coverage.
They complement each other.

**"Can I run it in CI on every build?"**
Yes, scoped to the modules you care about. `--format metrics-json` gives machine-readable
output. Comparing two runs (diffing call counts or p95) is the natural next feature.

**"Can I run it in production?"**
Not as a default, always-on tool. It's deterministic tracing. Use it in staging, on tests,
or briefly on one instance with tight `--root` / `--exclude`.

## Accuracy

**"Are the timings real if the tracer adds overhead?"**
They're corrected. At startup callgraph times its own per-call cost on a known workload
(about 1.5µs here), then subtracts it from every call based on how many calls happened
underneath it. `--no-calibrate` shows the raw numbers. In the worst case the corrected
total is about 1.6× real wall time, against about 8.7× uncorrected.
Counts are always exact.

**"Some functions show 0 ns or ~50 ns."**
That's below the clock resolution on Windows (about 100ns). Treat anything under about
200ns as "tiny". The call *count* is the useful signal there.

**"How is recursion handled?"**
Inclusive time only counts the outermost active call, so recursive calls aren't
double-counted (standard profiler semantics). The graph shows recursion as a self-loop.

**"Generators / async?"**
On 3.12+, a generator or coroutine resuming after a `yield` / `await` is *not* counted as
a new call, and its time is attributed correctly. The graph shows the synchronous stack,
not an async task graph (yet).

**"Threads?"**
All threads are traced with the default backend (3.12+), and each thread has its own stack.

**"Exceptions?"**
Calls that exit by raising are counted (the "Raised" stat) and the stack stays correct.
The bookstore's 422 validation errors show this.

## Scope / usage

**"Do I need to change my code?"**
No. `callgraph run script.py`, or wrap a block with `with callgraph.trace():`.

**"What does it trace by default?"**
Only code under the script's directory, so not stdlib or site-packages. Change that with
`--root`, `--exclude`, or `--include-site-packages`.

**"Does it work on Django / Flask / FastAPI / pytest?"**
Anything you can start as a Python script works. For frameworks, point it at the entry
script (for example `manage.py runserver --noreload`) and scope `--root` to your app package.
Native pytest support (`pytest --callgraph`) is a natural next step.

**"How big can a trace get?"**
Memory is bounded by the number of *distinct call paths*, not the number of calls
(750k calls produce 86 edges here). Per-call duration samples are capped and decimated per path.

**"Can I share the result?"**
Yes. The dashboard is one HTML file with no external requests, so you can attach it to a
PR, ticket or Slack message. It does embed function *source code*. Use `--no-source` if that matters.

**"What Python versions?"**
3.10+. 3.12+ gets the low-overhead `sys.monitoring` backend, and 3.10/3.11 fall back to `settrace`.

## Roadmap (when asked "what's next?")

1. More languages (JS/TS and Go are the most requested). The dashboard and metrics format
   are language-agnostic. Only the tracer is Python-specific.
2. Run-to-run diff: "this PR added 40k calls to `normalize`".
3. pytest plugin: per-test call graphs, plus "which tests exercise this function?"
4. C/Rust hot loop to bring the worst-case overhead toward cProfile's.
5. Async task graph view.

## If something goes wrong live

- **Dashboard didn't open:** open `demo/output/bookstore-dashboard.html` by hand.
- **Weird characters in the terminal:** set `$env:PYTHONIOENCODING="utf-8"` (the demo script already does).
- **Numbers differ from the slides:** "Timing depends on the machine. The *shape* is what matters." The counts will be identical, because the sample is deterministic.
