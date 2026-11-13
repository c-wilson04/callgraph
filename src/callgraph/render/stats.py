from __future__ import annotations

from typing import Any


def format_ns(ns: float) -> str:
    if ns >= 1e9:
        return f"{ns / 1e9:.2f} s"
    if ns >= 1e6:
        return f"{ns / 1e6:.2f} ms"
    if ns >= 1e3:
        return f"{ns / 1e3:.1f} µs"
    return f"{ns:.0f} ns"


def _table(headers: list[str], rows: list[list[str]], align: str) -> list[str]:
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]

    def fmt(cells: list[str]) -> str:
        out = []
        for cell, width, a in zip(cells, widths, align):
            out.append(cell.ljust(width) if a == "l" else cell.rjust(width))
        return "  ".join(out)

    return [fmt(headers), "  ".join("-" * w for w in widths), *(fmt(r) for r in rows)]


def render_stats(metrics: dict[str, Any], top: int = 10) -> str:
    s = metrics["summary"]
    funcs = list(metrics["functions"].values())
    labels = {f["key"]: f["label"] for f in funcs}
    lines = [
        f"callgraph · {s.get('script') or 'trace'} · backend={s['backend']} · Python {s['python']}",
        f"{s['total_calls']:,} calls · {s['unique_functions']} functions · "
        f"{s['edges']} call edges · max depth {s['max_depth']} · traced {format_ns(s['traced_ns'])}",
        "",
        f"Most called functions (top {top})",
    ]
    by_calls = sorted(funcs, key=lambda f: f["calls"], reverse=True)[:top]
    lines += _table(
        ["function", "calls", "mean", "median", "p95", "total", "self"],
        [
            [f["label"], f"{f['calls']:,}", format_ns(f["mean_ns"]), format_ns(f["median_ns"]),
             format_ns(f["p95_ns"]), format_ns(f["total_ns"]), format_ns(f["self_ns"])]
            for f in by_calls
        ],
        "lrrrrrr",
    )
    lines += ["", f"Most time spent (self time, top {top})"]
    by_self = sorted(funcs, key=lambda f: f["self_ns"], reverse=True)[:top]
    total_self = sum(f["self_ns"] for f in funcs) or 1
    lines += _table(
        ["function", "self", "share", "calls", "median"],
        [
            [f["label"], format_ns(f["self_ns"]), f"{100 * f['self_ns'] / total_self:.1f}%",
             f"{f['calls']:,}", format_ns(f["median_ns"])]
            for f in by_self
        ],
        "lrrrr",
    )
    hot = metrics["hot_paths"][: min(5, top)]
    if hot:
        lines += ["", "Hottest call paths"]
        for i, hp in enumerate(hot, 1):
            chain = " → ".join(labels.get(k, k) for k in hp["path"])
            lines.append(f"{i:>2}. ×{hp['calls']:,}  {chain}")
    return "\n".join(lines)
