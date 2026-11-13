from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FunctionIdentity:
    name: str
    qualified_name: str
    filename: str
    lineno: int
    module: str = ""

    @property
    def key(self) -> str:
        """Stable identifier for aggregating calls to the same function."""
        return f"{self.qualified_name}@{self.filename}:{self.lineno}"

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
    start_ns: int = 0
    end_ns: int = 0
    # A generator/coroutine resuming after a yield/await: same logical call, new segment.
    resumed: bool = False
    # Exited by an exception rather than a normal return.
    raised: bool = False

    @property
    def name(self) -> str:
        return self.identity.name

    @property
    def duration_ns(self) -> int:
        return max(0, self.end_ns - self.start_ns)

    @property
    def self_ns(self) -> int:
        return max(0, self.duration_ns - sum(child.duration_ns for child in self.children))

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.identity.name,
            "qualified_name": self.identity.qualified_name,
            "filename": self.identity.filename,
            "lineno": self.identity.lineno,
            "duration_ns": self.duration_ns,
            "children": [child.to_dict() for child in self.children],
        }
        if self.resumed:
            data["resumed"] = True
        if self.raised:
            data["raised"] = True
        return data


@dataclass(slots=True)
class CallTree:
    run_id: str
    root: CallTreeNode | None
    event_count: int = 0
    wall_ns: int = 0
    backend: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "event_count": self.event_count,
            "wall_ns": self.wall_ns,
            "backend": self.backend,
            "root": self.root.to_dict() if self.root else None,
        }
