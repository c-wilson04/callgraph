"""Aggregate a trace into metrics.

Works from a calling-context tree (CCT): the call tree with identical call paths merged,
so a function called 10,000 times from the same place is one node with ``calls=10000``.
Children keep first-seen order, so the CCT still reads as the program's pipeline.

Produces:

* per-function stats: calls, total (inclusive) time, self time, mean / median / p95 /
  min / max duration per call, exceptions raised;
* call edges: caller -> callee with call counts and time;
* the CCT itself (for the pipeline / flame view);
* hot paths: the most frequently executed root-to-leaf call chains.

Recursion is handled the standard profiler way: a function's inclusive time only counts
calls that are not nested inside another call to the same function.
"""

from __future__ import annotations

import inspect
import linecache
import os
import platform
import statistics
from typing import TYPE_CHECKING, Any

from callgraph.recorder import AggregateRecorder, CCTNode

if TYPE_CHECKING:
    from callgraph.model import CallTree, FunctionIdentity

SYNTHETIC = {"<program>"}
MAX_SOURCE_LINES = 80
MAX_SAMPLES = 400


def display_name(identity: FunctionIdentity) -> str:
    if identity.name == "<module>":
        if identity.module in ("", "__main__"):
            return f"{os.path.basename(identity.filename)} (main)"
        return f"{identity.module} <module>"
    qualified = identity.qualified_name
    if identity.module and qualified.startswith(identity.module + "."):
        qualified = qualified[len(identity.module) + 1 :]
    return qualified.replace(".<locals>.", ".")


def aggregate_tree(tree: CallTree) -> AggregateRecorder:
    """Replay a full per-call tree into an AggregateRecorder."""
    agg = AggregateRecorder()
    agg.backend = tree.backend
    if tree.root is None:
        return agg
    roots = tree.root.children if tree.root.identity.name in SYNTHETIC else [tree.root]
    stack: list[tuple[Any, bool]] = [(r, False) for r in reversed(roots)]
    while stack:
        node, exiting = stack.pop()
        if exiting:
            agg.on_return(node.end_ns, 0, node.raised)
            continue
        agg.on_call(node.identity, node.start_ns, 0, node.resumed)
        stack.append((node, True))
        stack.extend((child, False) for child in reversed(node.children))
    agg.count_events()
    return agg


def compute_metrics(
    source: CallTree | AggregateRecorder,
    *,
    include_source: bool = True,
    root_dir: str | None = None,
    script: str | None = None,
    hot_path_limit: int = 15,
    wall_ns: int = 0,
    backend: str | None = None,
) -> dict[str, Any]:
    if isinstance(source, AggregateRecorder):
        agg = source
        event_count = agg.event_count
    else:
        agg = aggregate_tree(source)
        event_count = source.event_count
        wall_ns = wall_ns or source.wall_ns
        backend = backend or source.backend

    calls: dict[FunctionIdentity, int] = {}
    total: dict[FunctionIdentity, int] = {}
    self_ns: dict[FunctionIdentity, int] = {}
    raised: dict[FunctionIdentity, int] = {}
    edges: dict[tuple[FunctionIdentity, FunctionIdentity], list[int]] = {}
    max_depth = 0

    # Iterative DFS over the CCT, tracking how many times each function is on the path.
    on_path: dict[FunctionIdentity, int] = {}
    stack: list[tuple[CCTNode, CCTNode | None, int, bool]] = [
        (child, None, 1, False) for child in reversed(list(agg.root.children.values()))
    ]
    while stack:
        node, parent, depth, exiting = stack.pop()
        ident = node.identity
        if exiting:
            on_path[ident] -= 1
            continue
        max_depth = max(max_depth, depth)
        calls[ident] = calls.get(ident, 0) + node.calls
        self_ns[ident] = self_ns.get(ident, 0) + node.self_ns
        raised[ident] = raised.get(ident, 0) + node.raised
        if not on_path.get(ident):
            total[ident] = total.get(ident, 0) + node.total_ns
        else:
            total.setdefault(ident, 0)
        if parent is not None:
            edge = edges.get((parent.identity, ident))
            if edge is None:
                edge = edges[(parent.identity, ident)] = [0, 0]
            edge[0] += node.calls
            edge[1] += node.total_ns
        on_path[ident] = on_path.get(ident, 0) + 1
        stack.append((node, parent, depth, True))
        for child in reversed(list(node.children.values())):
            stack.append((child, node, depth + 1, False))

    durations = agg.durations
    functions: dict[str, Any] = {}
    for ident, n_calls in calls.items():
        groups = durations.get(ident, [])
        values = sorted(v for samples, _ in groups for v in samples)
        n = len(values)
        median, p95 = _weighted_quantiles(groups, (0.5, 0.95))
        entry = {
            "key": ident.key,
            "name": ident.name,
            "label": display_name(ident),
            "qualified_name": ident.qualified_name,
            "module": ident.module,
            "filename": _relpath(ident.filename, root_dir),
            "lineno": ident.lineno,
            "calls": n_calls,
            "total_ns": total[ident],
            "self_ns": self_ns[ident],
            "mean_ns": int(total[ident] / n_calls) if n_calls else 0,
            "median_ns": median,
            "p95_ns": p95,
            "min_ns": values[0] if values else 0,
            "max_ns": values[-1] if values else 0,
            "raised": raised[ident],
            "samples": values if n <= MAX_SAMPLES
            else [values[(i * (n - 1)) // (MAX_SAMPLES - 1)] for i in range(MAX_SAMPLES)],
        }
        if include_source:
            entry["source"] = _source_for(ident)
        functions[ident.key] = entry

    edge_list = [
        {"source": src.key, "target": dst.key, "calls": v[0], "total_ns": v[1]}
        for (src, dst), v in edges.items()
    ]
    top_level = list(agg.root.children.values())
    traced_ns = sum(n.total_ns for n in top_level)

    return {
        "summary": {
            "script": script,
            "backend": backend or agg.backend,
            "python": platform.python_version(),
            "wall_ns": wall_ns or traced_ns,
            "traced_ns": traced_ns,
            "total_calls": sum(calls.values()),
            "unique_functions": len(calls),
            "edges": len(edge_list),
            "max_depth": max_depth,
            "events": event_count,
            "overhead_ns_per_call": getattr(agg, "overhead_ns", 0),
            "modules": sorted({i.module for i in calls if i.module}),
        },
        "functions": functions,
        "edges": edge_list,
        "cct": [_cct_to_dict(n) for n in top_level],
        "hot_paths": _hot_paths(agg.root, hot_path_limit),
    }


def _weighted_quantiles(groups: list[tuple[list[int], int]], qs: tuple[float, ...]) -> list[int]:
    if not groups:
        return [0 for _ in qs]
    if all(weight == 1 for _, weight in groups):
        values = sorted(v for samples, _ in groups for v in samples)
        n = len(values)
        out = []
        for q in qs:
            if q == 0.5:
                out.append(int(statistics.median(values)))
            else:
                out.append(values[min(n - 1, int(round(q * (n - 1))))])
        return out
    pairs = sorted((v, w) for samples, w in groups for v in samples)
    total = sum(w for _, w in pairs)
    out, acc, i = [], 0, 0
    for q in qs:
        target = q * total
        while i < len(pairs) - 1 and acc + pairs[i][1] < target:
            acc += pairs[i][1]
            i += 1
        out.append(pairs[i][0])
    return out


def _cct_to_dict(root: CCTNode) -> dict[str, Any]:
    def convert(node: CCTNode) -> dict[str, Any]:
        return {
            "key": node.identity.key,
            "calls": node.calls,
            "total_ns": node.total_ns,
            "self_ns": node.self_ns,
            "children": [],
        }

    out = convert(root)
    stack = [(root, out)]
    while stack:
        node, data = stack.pop()
        for child in node.children.values():
            child_data = convert(child)
            data["children"].append(child_data)
            stack.append((child, child_data))
    return out


def _hot_paths(root: CCTNode, limit: int) -> list[dict[str, Any]]:
    """Rank root-to-leaf call chains by how often the leaf was reached via that chain."""
    paths: list[tuple[int, int, list[str]]] = []
    stack = [(c, [c.identity.key]) for c in root.children.values()]
    while stack:
        node, path = stack.pop()
        if not node.children:
            paths.append((node.calls, node.total_ns, path))
        for child in node.children.values():
            stack.append((child, [*path, child.identity.key]))
    by_calls = sorted(paths, key=lambda p: (p[0], p[1]), reverse=True)[:limit]
    by_time = sorted(paths, key=lambda p: (p[1], p[0]), reverse=True)[:limit]
    seen, result = set(), []
    for calls, total, path in by_calls + by_time:
        if tuple(path) not in seen:
            seen.add(tuple(path))
            result.append({"path": path, "calls": calls, "total_ns": total})
    return result


def _relpath(filename: str, root_dir: str | None) -> str:
    if root_dir:
        try:
            rel = os.path.relpath(filename, root_dir)
            if not rel.startswith(".."):
                return rel.replace("\\", "/")
        except ValueError:
            pass
    return filename.replace("\\", "/")


def _source_for(identity: FunctionIdentity) -> str | None:
    lines = linecache.getlines(identity.filename)
    if not lines:
        return None
    if identity.name == "<module>":
        return "".join(lines[:MAX_SOURCE_LINES]).rstrip() or None
    start = max(identity.lineno - 1, 0)
    try:
        block = inspect.getblock(lines[start:])
    except Exception:
        block = lines[start : start + 20]
    text = "".join(block[:MAX_SOURCE_LINES]).rstrip()
    if len(block) > MAX_SOURCE_LINES:
        text += "\n    ..."
    return text or None
