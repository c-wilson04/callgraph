"""Exercise black: format black's own source files in memory (nothing is written).

Needs black installed from a source checkout (the PyPI wheel is compiled, so it can't be traced):
    git clone --depth 1 https://github.com/psf/black.git
    pip install -e ./black
Then (about 10 million calls for all files, so start small):
    callgraph run --root ./black/src --format html --open examples/real_world/drive_black.py 5
"""

import sys
from pathlib import Path

import black

SRC = Path(black.__file__).resolve().parent


def format_file(path, mode):
    source = path.read_text(encoding="utf-8")
    try:
        return black.format_str(source, mode=mode) != source
    except black.NothingChanged:
        return False


def main(limit=None):
    files = sorted(SRC.rglob("*.py"))[:limit]
    mode = black.Mode()
    changed = sum(format_file(path, mode) for path in files)
    print(f"formatted {len(files)} files, {changed} would change")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else None)
