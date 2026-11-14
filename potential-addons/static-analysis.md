# Static analysis: what could run vs. what did run

**Status:** idea, not started

## The problem

callgraph is purely dynamic. It only knows about calls that happened during the
recorded run, so code the run never touched is invisible. A function that is never
called and a function that simply wasn't exercised by this input look the same: absent.

## The idea

Build a *static* call graph by reading the source (every function defined, and every
call that could happen), then compare it with the dynamic graph from a real run:

```
static call graph  −  dynamic call graph  =  code that exists but never ran
```

What that unlocks:

- **Dead-code detection.** Run it on production-like traffic: functions defined but
  never called are candidates for deletion.
- **Call-level test coverage.** Run it on the test suite: "these functions are never
  called by any test." Pairs with the pytest-plugin roadmap item.
- **Fighting AI slop.** Agents often leave behind helpers and wrappers that nothing
  calls. This flags them directly, which fits the product's core pitch.
- **Unexercised edges.** A function that ran, but never from a caller the static graph
  says is possible (an error path, a fallback branch).

## Dynamic vs. static, for reference

| | Dynamic (today) | Static (this add-on) |
|---|---|---|
| Shows | What ran, on this input | Everything that could run |
| Exact counts and timings | Yes | No |
| Code that didn't execute | Invisible | Visible |
| `getattr`, plugins, callbacks, decorators | Handled, it sees the real call | Often missed or guessed |
| False paths | Never | Possible |

The two are complementary: static gives completeness, dynamic gives truth.

## How it could fit the architecture

- **New module `src/callgraph/static.py`.** Walk the files under `--root` with `ast`,
  collect every `FunctionDef` / `AsyncFunctionDef` (with its class nesting for the
  qualified name), and the `Call` nodes inside each one.
- **Reuse `TraceFilter`** so static and dynamic analysis cover exactly the same files.
- **Match on `FunctionIdentity.key`** (`qualified_name@filename:lineno`) so static
  functions line up with traced ones.
- **Output:** a "never ran" list in `stats`, a `never_ran` field in `metrics-json`, and
  dimmed / dashed nodes in the dashboard. Possibly its own command: `callgraph unused`.
- **Zero dependencies** stays true: `ast` is in the standard library.

## Gotchas already found

- **Line numbers don't match for decorated functions.** The traced key uses the code
  object's `co_firstlineno`, which is the line of the *first decorator*. `ast` gives the
  `def` line as `lineno`. Use `min(d.lineno for d in node.decorator_list)` when a
  function has decorators. (Verified on Python 3.13.)
- **Resolving calls is the hard part.** `foo()` is easy. `self.foo()` needs class
  resolution, `obj.foo()` needs type inference, and `getattr(obj, name)()` is
  impossible statically. A first version can list *definitions* only (enough for
  "never ran") and leave edge resolution for later.
- **Entry points look unused.** CLI commands, web route handlers, `__main__` blocks,
  test functions and plugin hooks are called by frameworks, not by your code. They need
  an allowlist or a decorator-based heuristic, or the report fills with false alarms.
- **Never-ran depends on the input.** The report must say "not called during this run",
  never "unused", unless the run is known to be representative.

## Open questions

- Definitions-only first, or attempt call-edge resolution from the start?
- Should an existing tool (e.g. `pyan`, `jedi`) be optional for better resolution,
  given the zero-dependency rule?
- How should the dashboard show hundreds of never-ran functions without drowning the
  ones that did run?
- Is "never ran" more useful per run, or accumulated across many runs (e.g. a week of
  production traffic)?
