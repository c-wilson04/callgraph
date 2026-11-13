# AGENTS.md

## Cursor Cloud specific instructions

`callgraph` is a dependency-free Python package (a dynamic runtime call graph tracer and profiler) with a CLI and a self-contained HTML dashboard. There is no server or database — verify changes with `pytest` and by running the CLI. The only dev dependency is `pytest`.

### Environment

- Python 3.12 (repo requires `>=3.10`). Dependencies live in an isolated virtualenv at `.venv/` (created by the startup update script). Activate it with `. .venv/bin/activate`, or call tools directly via `.venv/bin/pytest` / `.venv/bin/callgraph`.
- The package is installed editable (`pip install -e ".[dev]"`), so source edits under `src/callgraph/` take effect immediately without reinstalling.

### Test / run

- Tests: `pytest` (config in `pyproject.toml`, tests in `tests/`).
- Run the app: `callgraph run examples/abc_demo.py` or `python -m callgraph run examples/abc_demo.py`. See `README.md` for output formats and filtering flags.

### Non-obvious gotchas

- CLI flags may go before or after the script path; unknown tokens after the script are forwarded to it, and everything after `--` is forwarded verbatim (`cli._split_argv`).
- `stats` / `html` / `ascii` / `metrics-json` use the low-overhead `AggregateRecorder`; only `json` / `mermaid` / `events` build the full per-call tree.
- The `sys.monitoring` hot path (`instrumentation.MonitoringTracer._make_aggregate_callbacks`) is deliberately inlined and keyed by `id(code)`; benchmark with `callgraph bench examples/bookstore/app.py --no-latency` before and after touching it.
- The dashboard is a single template (`src/callgraph/render/dashboard.html`) with data injected at `/*__CALLGRAPH_DATA__*/null`; it must stay dependency-free (no CDN) so reports work offline.

### Lint

- No linter/formatter is configured in this repo (no ruff/flake8/black/pre-commit).
