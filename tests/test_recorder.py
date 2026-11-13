import json
import subprocess
import sys
from pathlib import Path

import pytest

from callgraph.events import EventType, TraceEvent
from callgraph.filters import TraceFilter
from callgraph.instrumentation import run_script
from callgraph.model import FunctionIdentity
from callgraph.recorder import ExecutionRecorder
from callgraph.render.ascii import render_ascii
from callgraph.api import build_call_tree


ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "abc_demo.py"


def _identity(name: str) -> FunctionIdentity:
    return FunctionIdentity(
        name=name,
        qualified_name=f"demo.{name}",
        filename="/demo.py",
        lineno=1,
    )


def test_recorder_builds_tree_from_events():
    recorder = ExecutionRecorder()
    events = [
        TraceEvent(EventType.CALL, _identity("a")),
        TraceEvent(EventType.CALL, _identity("b")),
        TraceEvent(EventType.CALL, _identity("d")),
        TraceEvent(EventType.RETURN, _identity("d")),
        TraceEvent(EventType.RETURN, _identity("b")),
        TraceEvent(EventType.CALL, _identity("c")),
        TraceEvent(EventType.RETURN, _identity("c")),
        TraceEvent(EventType.RETURN, _identity("a")),
    ]
    root = recorder.feed(events)
    assert root is not None
    assert root.name == "a"
    assert [child.name for child in root.children] == ["b", "c"]
    assert root.children[0].children[0].name == "d"


def test_abc_demo_integration():
    recorder = run_script(EXAMPLE, trace_filter=TraceFilter.for_script(EXAMPLE))
    tree = build_call_tree(recorder)
    ascii_output = render_ascii(tree)

    assert "a" in ascii_output
    assert "b" in ascii_output
    assert "c" in ascii_output
    assert "d" in ascii_output

    root = tree.root
    assert root is not None
    effective = root if root.name != "<module>" else root.children[0]
    assert effective.name == "a"
    assert [child.name for child in effective.children] == ["b", "c"]
    assert effective.children[0].children[0].name == "d"


def test_cli_ascii_output():
    result = subprocess.run(
        [sys.executable, "-m", "callgraph", "run", str(EXAMPLE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={**dict(**{"PYTHONPATH": str(ROOT / "src")}), **dict(__import__("os").environ)},
    )
    output = result.stdout
    assert "a" in output
    assert "b" in output
    assert "d" in output
    assert "c" in output


def test_filter_excludes_stdlib(tmp_path):
    script = tmp_path / "stdlib_demo.py"
    script.write_text(
        "import json\n\ndef main():\n    json.dumps({'a': 1})\n\nmain()\n",
        encoding="utf-8",
    )
    recorder = run_script(script, trace_filter=TraceFilter.for_script(script))
    tree = build_call_tree(recorder)
    names = _collect_names(tree.root)
    assert "main" in names
    assert "dumps" not in names


def _collect_names(node) -> list[str]:
    if node is None:
        return []
    names = [node.name]
    for child in node.children:
        names.extend(_collect_names(child))
    return names
