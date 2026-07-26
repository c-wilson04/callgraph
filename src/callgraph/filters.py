from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _normalize_path(path: str) -> str:
    if path.startswith("<"):
        return path
    return os.path.abspath(path)


@dataclass(slots=True)
class TraceFilter:
    """Filter trace events to user code by default."""

    root: Path | None = None
    include_site_packages: bool = False
    exclude_patterns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.root is not None:
            self.root = self.root.resolve()

    def should_trace(self, filename: str) -> bool:
        if filename.startswith("<"):
            return False

        normalized = _normalize_path(filename)

        for pattern in self.exclude_patterns:
            if pattern in normalized:
                return False

        if not self.include_site_packages:
            if "site-packages" in normalized:
                return False
            if normalized.startswith(sys.base_prefix):
                return False

        if self.root is not None:
            try:
                Path(normalized).resolve().relative_to(self.root)
            except ValueError:
                return False

        return True

    @classmethod
    def for_script(cls, script_path: Path, **kwargs: object) -> TraceFilter:
        return cls(root=script_path.parent.resolve(), **kwargs)
