# AGENTS.md

## Cursor Cloud specific instructions

`callgraph` is a dependency-free, terminal-only Python package (a dynamic runtime call graph tracer). There is no GUI, server, or database — verify changes with `pytest` and by running the CLI. The only dev dependency is `pytest`.

### Environment

- Python 3.12 (repo requires `>=3.10`). Dependencies live in an isolated virtualenv at `.venv/` (created by the startup update script). Activate it with `. .venv/bin/activate`, or call tools directly via `.venv/bin/pytest` / `.venv/bin/callgraph`.
- The package is installed editable (`pip install -e ".[dev]"`), so source edits under `src/callgraph/` take effect immediately without reinstalling.

### Test / run

- Tests: `pytest` (config in `pyproject.toml`, tests in `tests/`).
- Run the app: `callgraph run examples/abc_demo.py` or `python -m callgraph run examples/abc_demo.py`. See `README.md` for output formats and filtering flags.

### Non-obvious gotcha

- The `run` subcommand defines `script_args` with `argparse.REMAINDER`, so any flag placed **after** the script path (e.g. `... abc_demo.py --format json`) is captured as an argument forwarded to the traced script and silently ignored by the CLI (you get default `ascii` output). Put CLI flags **before** the script path: `callgraph run --format json examples/abc_demo.py`.

### Lint

- No linter/formatter is configured in this repo (no ruff/flake8/black/pre-commit).
