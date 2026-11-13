"""Exercise rich: render a 300-row table, a Markdown document and a tree (output discarded).

Needs rich installed from a source checkout so its code can be traced:
    git clone --depth 1 https://github.com/Textualize/rich.git
    pip install -e ./rich
Then:
    callgraph run --root ./rich/rich --format html --open examples/real_world/drive_rich.py
"""

import io

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.tree import Tree

DOC = """
# Release notes

Rich makes **terminals** beautiful. This document mixes *emphasis*, `code`, lists and quotes.

## Highlights

- Tables with styled cells
- Markdown rendering
- Trees, panels and progress bars

> Measure twice, render once.

```python
from rich import print
print("[bold magenta]Hello[/bold magenta] world")
```
""" * 6


def render_table(console, rows=300):
    table = Table(title="Orders")
    for name in ("id", "customer", "item", "qty", "price", "status"):
        table.add_column(name)
    for i in range(rows):
        table.add_row(str(i), f"customer {i % 37}", f"[bold]item {i % 11}[/bold]", str(i % 5 + 1),
                      f"${(i * 7.31) % 100:.2f}", "[green]paid[/green]" if i % 3 else "[red]due[/red]")
    console.print(table)


def render_markdown(console):
    console.print(Markdown(DOC))


def render_tree(console, depth=4, width=4):
    root = Tree("project")

    def grow(node, level):
        if level == depth:
            return
        for i in range(width):
            grow(node.add(f"[cyan]dir {level}.{i}"), level + 1)

    grow(root, 0)
    console.print(root)


def main():
    console = Console(file=io.StringIO(), width=120, force_terminal=True, color_system="truecolor")
    render_table(console)
    render_markdown(console)
    render_tree(console)
    print(f"rendered {len(console.file.getvalue()):,} characters")


if __name__ == "__main__":
    main()
