from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from callgraph.api import build_call_tree
from callgraph.filters import TraceFilter
from callgraph.instrumentation import run_script
from callgraph.render.ascii import render_ascii
from callgraph.render.events import render_events
from callgraph.render.json import render_json
from callgraph.render.mermaid import render_mermaid


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="callgraph",
        description="Record runtime Python call graphs from execution.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Trace a Python script")
    run_parser.add_argument("script", type=Path, help="Path to the script to trace")
    run_parser.add_argument(
        "script_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to the script",
    )
    run_parser.add_argument(
        "--format",
        choices=("ascii", "json", "mermaid", "events"),
        default="ascii",
        help="Output format (default: ascii)",
    )
    run_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Root directory for user-code filtering (default: script directory)",
    )
    run_parser.add_argument(
        "--include-site-packages",
        action="store_true",
        help="Include third-party packages in the trace",
    )
    run_parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        dest="exclude_patterns",
        help="Exclude paths containing this substring (repeatable)",
    )
    run_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print tracing stats to stderr",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return _run_command(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def _run_command(args: argparse.Namespace) -> int:
    script_path: Path = args.script
    if not script_path.exists():
        print(f"error: script not found: {script_path}", file=sys.stderr)
        return 1

    script_args = args.script_args
    if script_args and script_args[0] == "--":
        script_args = script_args[1:]

    root = args.root.resolve() if args.root else script_path.parent.resolve()
    trace_filter = TraceFilter(
        root=root,
        include_site_packages=args.include_site_packages,
        exclude_patterns=args.exclude_patterns,
    )

    captured_events = [] if args.format == "events" else None
    event_sink = captured_events.append if captured_events is not None else None

    started = time.perf_counter()
    try:
        recorder = run_script(
            script_path,
            script_args=script_args,
            trace_filter=trace_filter,
            event_sink=event_sink,
        )
    except Exception as exc:
        print(f"error: script failed: {exc}", file=sys.stderr)
        return 1

    elapsed_ms = (time.perf_counter() - started) * 1000
    call_tree = build_call_tree(recorder)

    if args.format == "json":
        print(render_json(call_tree))
    elif args.format == "mermaid":
        print(render_mermaid(call_tree))
    elif args.format == "events":
        print(render_events(call_tree, captured_events or []))
    else:
        print(render_ascii(call_tree))

    if args.verbose:
        print(
            f"# {call_tree.event_count} events recorded in {elapsed_ms:.1f} ms",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
