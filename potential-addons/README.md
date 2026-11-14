# Potential add-ons

Ideas that could extend callgraph but are not built or committed to. Each file is a
short proposal: the problem, what the add-on would do, how it fits the current
architecture, and the open questions.

An idea moves out of this folder when it is either built (record the design decision
in `docs/decisions/`) or dropped (delete the file, git keeps the history).

| Add-on | One line | Status |
|---|---|---|
| [Static analysis](static-analysis.md) | Compare what *could* be called with what *did* run, to find dead code and untested functions | Idea |

The README's "Next up" list (more language tracers, run-to-run diffs, a pytest plugin,
a native hot loop) holds the other candidates.
