from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from callgraph.api import build_call_tree
from callgraph.filters import TraceFilter
from callgraph.recorder import AggregateRecorder, ExecutionRecorder
from callgraph.instrumentation import BACKENDS, HAS_MONITORING, resolve_backend, run_script
from callgraph.render.ascii import render_ascii
from callgraph.render.events import render_events
from callgraph.render.json import render_json
from callgraph.render.mermaid import render_mermaid
from callgraph.render.stats import format_ns, render_stats

FULL_TREE_FORMATS = ("json", "mermaid", "events")
FORMATS = ("ascii", "stats", "html", "json", "metrics-json", "mermaid", "events", "none")

# Options that consume a value. Used to locate the script path so that callgraph flags
# work both before and after it:  `callgraph run --format html app.py` and
# `callgraph run app.py --format html` are equivalent. Anything after `--` goes to the
# traced script untouched.
_VALUE_OPTS = {"--format", "-f", "--root", "--exclude", "--backend", "-o", "--output", "--top", "--repeat"}
_FLAG_OPTS = {"--include-site-packages", "--verbose", "-v", "--open", "--no-source", "--no-calibrate",
              "--timing-json", "-h", "--help"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="callgraph",
        description="Record runtime Python call graphs and performance metrics from real executions.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("script", type=Path, help="Path to the script to trace")
        p.add_argument("--root", type=Path, default=None,
                       help="Root directory for user-code filtering (default: script directory)")
        p.add_argument("--include-site-packages", action="store_true",
                       help="Include third-party packages in the trace")
        p.add_argument("--exclude", action="append", default=[], dest="exclude_patterns",
                       help="Exclude paths containing this substring (repeatable)")
        p.add_argument("--backend", choices=BACKENDS, default="auto",
                       help="Tracing backend: monitoring (3.12+, low overhead), settrace, or none "
                            "(default: auto)")

    run_parser = subparsers.add_parser("run", help="Trace a Python script")
    add_common(run_parser)
    run_parser.add_argument("--format", "-f", choices=FORMATS, default="ascii",
                            help="Output format (default: ascii)")
    run_parser.add_argument("--output", "-o", type=Path, default=None,
                            help="Write output to this file (html defaults to callgraph-<script>.html)")
    run_parser.add_argument("--open", action="store_true", help="Open the HTML dashboard in a browser")
    run_parser.add_argument("--top", type=int, default=10, help="Rows per table in stats output")
    run_parser.add_argument("--no-source", action="store_true",
                            help="Do not embed function source code in html / metrics-json")
    run_parser.add_argument("--no-calibrate", action="store_true",
                            help="Do not subtract measured instrumentation overhead from timings")
    run_parser.add_argument("--verbose", "-v", action="store_true", help="Print tracing stats to stderr")
    run_parser.add_argument("--timing-json", action="store_true", help=argparse.SUPPRESS)

    bench_parser = subparsers.add_parser(
        "bench", help="Measure tracing overhead: run a script untraced and under each backend"
    )
    add_common(bench_parser)
    bench_parser.add_argument("--repeat", type=int, default=5, help="Runs per backend (default: 5)")

    return parser


def _split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split argv into (callgraph args, traced-script args)."""
    if not argv or argv[0] not in ("run", "bench"):
        return argv, []
    ours = [argv[0]]
    script_args: list[str] = []
    i, found_script = 1, False
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            if found_script:
                script_args.extend(argv[i + 1 :])
                break
            i += 1
            continue
        name = tok.split("=", 1)[0]
        if name in _VALUE_OPTS:
            ours.append(tok)
            if "=" not in tok and i + 1 < len(argv):
                ours.append(argv[i + 1])
                i += 1
        elif name in _FLAG_OPTS:
            ours.append(tok)
        elif not found_script:
            ours.append(tok)
            found_script = True
        else:
            script_args.append(tok)
        i += 1
    return ours, script_args


def _configure_stdio() -> None:
    # On Windows, piped stdout defaults to the ANSI code page (cp1252), which can't
    # encode the box-drawing characters in the ASCII tree.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            if (stream.encoding or "").lower().replace("-", "") != "utf8" and not stream.isatty():
                reconfigure(encoding="utf-8", errors="replace")
            else:
                reconfigure(errors="replace")
        except (ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    ours, script_args = _split_argv(argv)
    parser = _build_parser()
    args = parser.parse_args(ours)
    args.script_args = script_args

    if args.command == "run":
        return _run_command(args)
    if args.command == "bench":
        return _bench_command(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def _run_command(args: argparse.Namespace) -> int:
    script_path: Path = args.script
    if not script_path.exists():
        print(f"error: script not found: {script_path}", file=sys.stderr)
        return 1
    try:
        backend = resolve_backend(args.backend)
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    root = args.root.resolve() if args.root else script_path.parent.resolve()
    trace_filter = TraceFilter(
        root=root,
        include_site_packages=args.include_site_packages,
        exclude_patterns=args.exclude_patterns,
    )

    captured_events: list | None = [] if args.format == "events" else None
    event_sink = captured_events.append if captured_events is not None else None

    # Full per-call trees are only needed for json / mermaid / events; everything else
    # aggregates on the fly, which is much cheaper in time and memory.
    recorder = ExecutionRecorder() if args.format in FULL_TREE_FORMATS else AggregateRecorder()
    overhead = (0, 0)
    if isinstance(recorder, AggregateRecorder) and not args.no_calibrate and args.format != "none":
        from callgraph.calibrate import calibrate

        overhead = calibrate(backend, root)
        recorder.sample_correction = overhead

    started = time.perf_counter_ns()
    try:
        run_script(
            script_path,
            script_args=args.script_args,
            trace_filter=trace_filter,
            event_sink=event_sink,
            backend=backend,
            recorder=recorder,
        )
    except Exception as exc:
        print(f"error: script failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    elapsed_ns = time.perf_counter_ns() - started

    if isinstance(recorder, AggregateRecorder) and overhead != (0, 0):
        from callgraph.calibrate import apply_overhead_correction

        apply_overhead_correction(recorder, overhead)

    if args.timing_json:
        print(json.dumps({"elapsed_ns": elapsed_ns, "backend": backend}), file=sys.stderr)

    output = _render(args, recorder, captured_events, root, script_path, elapsed_ns)

    if output is not None:
        out_path: Path | None = args.output
        if args.format == "html" and out_path is None:
            out_path = Path(f"callgraph-{script_path.stem}.html")
        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output + "\n", encoding="utf-8")
            print(f"callgraph: wrote {out_path}", file=sys.stderr)
            if args.open:
                webbrowser.open(out_path.resolve().as_uri())
        else:
            print(output)

    if args.verbose:
        print(
            f"# {recorder.event_count:,} events recorded in {format_ns(elapsed_ns)} "
            f"(backend: {backend})",
            file=sys.stderr,
        )

    return 0


def _render(args, recorder, captured_events, root: Path, script_path: Path, elapsed_ns: int) -> str | None:
    fmt = args.format
    if fmt == "none":
        return None
    if fmt in FULL_TREE_FORMATS:
        call_tree = build_call_tree(recorder, wall_ns=elapsed_ns)
    if fmt == "json":
        return render_json(call_tree)
    if fmt == "mermaid":
        return render_mermaid(call_tree)
    if fmt == "events":
        return render_events(call_tree, captured_events or [])
    if fmt == "ascii":
        return render_ascii(recorder)

    from callgraph.metrics import compute_metrics

    metrics = compute_metrics(
        recorder,
        wall_ns=elapsed_ns,
        include_source=not args.no_source,
        root_dir=str(root),
        script=script_path.name,
    )
    if fmt == "stats":
        return render_stats(metrics, top=args.top)
    if fmt == "metrics-json":
        return json.dumps(metrics, indent=2)
    from callgraph.render.html import render_html

    return render_html(metrics)


def _bench_command(args: argparse.Namespace) -> int:
    script_path: Path = args.script
    if not script_path.exists():
        print(f"error: script not found: {script_path}", file=sys.stderr)
        return 1
    backends = ["none", "settrace"] + (["monitoring"] if HAS_MONITORING else [])
    base_cmd = [sys.executable, "-m", "callgraph", "run", "--format", "none", "--timing-json"]
    if args.root:
        base_cmd += ["--root", str(args.root)]
    if args.include_site_packages:
        base_cmd.append("--include-site-packages")
    for pattern in args.exclude_patterns:
        base_cmd += ["--exclude", pattern]

    env = dict(os.environ)
    src_dir = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = src_dir + os.pathsep + env.get("PYTHONPATH", "")

    print(f"Benchmarking {script_path} ({args.repeat} runs per mode, median shown)\n")
    results: dict[str, float] = {}
    for backend in backends:
        times = []
        for _ in range(max(1, args.repeat)):
            proc = subprocess.run(
                [*base_cmd, "--backend", backend, str(script_path), "--", *args.script_args],
                capture_output=True, text=True, env=env, encoding="utf-8", errors="replace",
            )
            line = next((l for l in reversed(proc.stderr.splitlines()) if l.startswith("{")), None)
            if proc.returncode != 0 or line is None:
                print(f"error: {backend} run failed:\n{proc.stderr}", file=sys.stderr)
                return 1
            times.append(json.loads(line)["elapsed_ns"])
        results[backend] = statistics.median(times)

    baseline = results["none"]
    label = {"none": "untraced", "settrace": "settrace", "monitoring": "sys.monitoring"}
    print(f"{'mode':<16}{'median':>12}{'overhead':>12}")
    print(f"{'-' * 16}{'-' * 12}{'-' * 12}")
    for backend, value in results.items():
        overhead = "baseline" if backend == "none" else f"{value / baseline:.2f}x"
        print(f"{label[backend]:<16}{format_ns(value):>12}{overhead:>12}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
