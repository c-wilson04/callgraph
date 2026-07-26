# Callgraph

Dynamic runtime call graph tracer for Python. Records **what actually executed** — not what a static analyzer thinks might run.

## Phase 1

This milestone implements the core event pipeline:

```
Program Execution → sys.settrace → Execution Recorder → Call Tree → ASCII / JSON / Mermaid
```

Only **call** and **return** events are captured. Variables, timing, loops, conditionals, async, and multi-threading are deferred to later phases.

## Install

```bash
pip install -e ".[dev]"
```

## Usage

Trace a script and print an ASCII call tree:

```bash
python -m callgraph run examples/abc_demo.py
```

Expected output:

```
a
├── b
│   └── d
└── c
```

Other output formats:

```bash
python -m callgraph run examples/abc_demo.py --format json
python -m callgraph run examples/abc_demo.py --format mermaid
python -m callgraph run examples/abc_demo.py --format events
```

### Filtering

By default, only code under the script's directory is traced. Standard library and site-packages calls are excluded.

```bash
python -m callgraph run myscript.py --root /path/to/project
python -m callgraph run myscript.py --include-site-packages
python -m callgraph run myscript.py --exclude tests/
```

### Programmatic API

```python
from callgraph import trace, build_call_tree
from callgraph.render.ascii import render_ascii

with trace() as recorder:
    main()

tree = build_call_tree(recorder)
print(render_ascii(tree))
```

## Architecture

| Layer | Module | Responsibility |
|-------|--------|----------------|
| Instrumentation | `instrumentation.py` | `sys.settrace` hook, frame → identity |
| Filtering | `filters.py` | Include/exclude by path |
| Recorder | `recorder.py` | Stack-based tree builder |
| Model | `model.py` | `CallTreeNode`, serialization |
| Render | `render/` | ASCII, JSON, Mermaid, events |
| CLI | `cli.py` | `python -m callgraph run` |

## Limitations (Phase 1)

- **Overhead:** `sys.settrace` significantly slows execution.
- **Threads:** Only the main thread is traced.
- **Async:** `asyncio` tasks are not reliably traced.
- **C extensions:** Native code is invisible to the tracer.
- **Recursion:** Full tree is recorded (no collapse yet).

## Development

```bash
pytest
```
