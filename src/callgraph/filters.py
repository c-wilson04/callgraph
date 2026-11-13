from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_PACKAGE_DIR = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))


def _normalize_path(path: str) -> str:
    if path.startswith("<"):
        return path
    return os.path.normcase(os.path.abspath(path))


@dataclass(slots=True)
class TraceFilter:
    """Filter trace events to user code by default.

    Decisions are cached per filename: the filter runs on every call event, so the
    path work (abspath / resolve) must happen once per file, not once per call.
    """

    root: Path | None = None
    include_site_packages: bool = False
    exclude_patterns: list[str] = field(default_factory=list)
    _cache: dict[str, bool] = field(default_factory=dict, repr=False)
    _root_str: str | None = field(default=None, repr=False)
    _prefixes: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if self.root is not None:
            self.root = self.root.resolve()
            self._root_str = os.path.normcase(str(self.root))
        prefixes = {sys.base_prefix, sys.base_exec_prefix, sys.prefix, sys.exec_prefix}
        # Only treat the interpreter's own install as stdlib when the user's root
        # isn't inside it (e.g. a project checked out under the Python directory).
        self._prefixes = tuple(
            os.path.normcase(os.path.abspath(p)) for p in prefixes if p
        )

    def should_trace(self, filename: str) -> bool:
        cached = self._cache.get(filename)
        if cached is None:
            cached = self._cache[filename] = self._decide(filename)
        return cached

    def _decide(self, filename: str) -> bool:
        if filename.startswith("<"):
            return False

        normalized = _normalize_path(filename)

        if _is_within(normalized, _PACKAGE_DIR):
            return False  # never trace the tracer itself

        for pattern in self.exclude_patterns:
            if pattern in normalized or os.path.normcase(pattern) in normalized:
                return False

        if not self.include_site_packages:
            if "site-packages" in normalized or "dist-packages" in normalized:
                return False
            root_in_prefix = self._root_str is not None and any(
                _is_within(self._root_str, prefix) for prefix in self._prefixes
            )
            if not root_in_prefix and any(
                _is_within(normalized, prefix) for prefix in self._prefixes
            ):
                return False

        if self._root_str is not None:
            if not _is_within(normalized, self._root_str):
                # Slow path: symlinks / junctions.
                try:
                    Path(normalized).resolve().relative_to(self.root)  # type: ignore[arg-type]
                except (ValueError, OSError):
                    return False

        return True

    @classmethod
    def for_script(cls, script_path: Path, **kwargs: object) -> TraceFilter:
        return cls(root=script_path.parent.resolve(), **kwargs)


def _is_within(path: str, directory: str) -> bool:
    if path == directory:
        return True
    directory = directory.rstrip("\\/")
    return path.startswith(directory + os.sep) or path.startswith(directory + "/")
