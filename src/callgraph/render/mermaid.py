from __future__ import annotations

import re

from callgraph.model import CallTree, CallTreeNode


def _sanitize_id(name: str, index: int) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return f"{cleaned}_{index}"


def render_mermaid(tree: CallTree) -> str:
    roots = _effective_roots(tree.root)
    if not roots:
        return "graph TD\n    empty[\"(empty call tree)\"]"

    lines = ["graph TD"]
    node_ids: dict[int, str] = {}
    counter = 0

    def node_id(node: CallTreeNode) -> str:
        nonlocal counter
        key = id(node)
        if key not in node_ids:
            node_ids[key] = _sanitize_id(node.identity.name, counter)
            counter += 1
        return node_ids[key]

    def walk(node: CallTreeNode) -> None:
        nid = node_id(node)
        label = node.identity.name.replace('"', "'")
        lines.append(f'    {nid}["{label}"]')
        for child in node.children:
            cid = node_id(child)
            walk(child)
            lines.append(f"    {nid} --> {cid}")

    for root in roots:
        walk(root)

    return "\n".join(lines)


def _effective_roots(node: CallTreeNode | None) -> list[CallTreeNode]:
    if node is None:
        return []
    if node.identity.name == "<module>":
        return node.children
    return [node]
