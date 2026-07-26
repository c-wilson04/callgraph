from __future__ import annotations

import json
from typing import Any

from callgraph.model import CallTree, CallTreeNode


def render_json(tree: CallTree, *, indent: int = 2) -> str:
    return json.dumps(tree.to_dict(), indent=indent)


def render_json_node(node: CallTreeNode) -> dict[str, Any]:
    return node.to_dict()
