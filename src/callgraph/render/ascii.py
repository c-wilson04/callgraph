from __future__ import annotations

from callgraph.model import CallTree, CallTreeNode


def _effective_roots(node: CallTreeNode | None) -> list[CallTreeNode]:
    if node is None:
        return []
    if node.identity.name == "<module>":
        return node.children
    return [node]


def render_ascii(tree: CallTree) -> str:
    roots = _effective_roots(tree.root)
    if not roots:
        return "(empty call tree)"
    if len(roots) == 1:
        return _render_subtree(roots[0], prefix="", is_last=True, is_root=True)
    return "\n\n".join(
        _render_subtree(root, prefix="", is_last=(index == len(roots) - 1), is_root=True)
        for index, root in enumerate(roots)
    )


def _render_subtree(
    node: CallTreeNode,
    prefix: str,
    is_last: bool,
    is_root: bool,
) -> str:
    lines: list[str] = []
    if is_root:
        lines.append(node.identity.name)
        child_prefix = ""
    else:
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{node.identity.name}")
        child_prefix = prefix + ("    " if is_last else "│   ")

    child_count = len(node.children)
    for index, child in enumerate(node.children):
        lines.append(
            _render_subtree(
                child,
                child_prefix,
                is_last=(index == child_count - 1),
                is_root=False,
            )
        )
    return "\n".join(lines)
