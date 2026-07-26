from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FunctionIdentity:
    name: str
    qualified_name: str
    filename: str
    lineno: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "filename": self.filename,
            "lineno": self.lineno,
        }


@dataclass(slots=True)
class CallTreeNode:
    identity: FunctionIdentity
    children: list[CallTreeNode] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.identity.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.identity.name,
            "qualified_name": self.identity.qualified_name,
            "filename": self.identity.filename,
            "lineno": self.identity.lineno,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(slots=True)
class CallTree:
    run_id: str
    root: CallTreeNode | None
    event_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "event_count": self.event_count,
            "root": self.root.to_dict() if self.root else None,
        }
