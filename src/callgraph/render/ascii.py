from __future__ import annotations

from typing import TYPE_CHECKING

from callgraph.recorder import AggregateRecorder, CCTNode

if TYPE_CHECKING:
    from callgraph.model import CallTree

MAX_LINES = 400


def _effective_roots(root: CCTNode) -> list[CCTNode]:
    roots: list[CCTNode] = []
    for node in root.children.values():
        if node.identity is not None and node.identity.name == "<module>":
            roots.extend(node.children.values())
        else:
            roots.append(node)
    return roots


def render_ascii(source: CallTree | AggregateRecorder, max_lines: int = MAX_LINES) -> str:
    """Render the call tree, merging repeated calls along the same path as ``name ×N``."""
    if isinstance(source, AggregateRecorder):
        agg = source
    else:
        from callgraph.metrics import aggregate_tree

        agg = aggregate_tree(source)

    roots = _effective_roots(agg.root)
    if not roots:
        return "(empty call tree)"

    lines: list[str] = []
    truncated = 0

    def label(node: CCTNode) -> str:
        name = node.identity.name  # type: ignore[union-attr]
        return f"{name} ×{node.calls:,}" if node.calls > 1 else name

    def walk(node: CCTNode, prefix: str, is_last: bool, is_root: bool) -> None:
        nonlocal truncated
        if len(lines) >= max_lines:
            truncated += 1
            for child in node.children.values():
                walk(child, "", True, False)
            return
        if is_root:
            lines.append(label(node))
            child_prefix = ""
        else:
            lines.append(f"{prefix}{'└── ' if is_last else '├── '}{label(node)}")
            child_prefix = prefix + ("    " if is_last else "│   ")
        children = list(node.children.values())
        for index, child in enumerate(children):
            walk(child, child_prefix, index == len(children) - 1, False)

    for index, root in enumerate(roots):
        if index and len(lines) < max_lines:
            lines.append("")
        walk(root, "", True, True)

    if truncated:
        lines.append(f"… {truncated:,} more call paths (use --format stats or html for the full picture)")
    return "\n".join(lines)
