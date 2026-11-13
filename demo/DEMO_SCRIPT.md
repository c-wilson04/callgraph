# callgraph: 5-minute demo script

**Audience:** engineers and testers who build and run code daily.
**Goal:** they understand what it shows, see why runtime paths matter, trust the numbers,
and want to try it on their own code (approve, adopt, give feedback).
**Format:** pre-recorded video (about 4:30), reproducible live with `demo/run-demo.ps1`.

---

## Before you record

- [ ] `powershell -ExecutionPolicy Bypass -File demo\run-demo.ps1 -NoPause` once, to warm
      up the venv and pip cache so nothing installs on camera.
- [ ] Terminal font 18–20pt, dark theme, window about 1600×900. Close notifications.
- [ ] Browser at 100% zoom, full screen (F11). Dark mode matches the terminal.
- [ ] Open `examples/bookstore/` in your editor so you can flash the folder structure.
- [ ] Do one dry run with a timer. Each section below has a target time.
- [ ] Have `demo/output/bookstore-dashboard.html` already generated as a fallback.

Numbers below come from this machine (Windows, Python 3.13). Yours will be close but not
identical. Say "about" and round them.

---

## 0:00–0:25 · Hook (talking head or title slide)

> "When something is slow or broken, the first question is always: *what actually ran?*
> Not what the code *could* do. Which functions ran, in what order, how many times, and
> where the time went. Static call graphs can't tell you that. Profilers give you a table.
> callgraph records a real run and shows you the whole pipeline."

## 0:25–0:55 · Beat 1: a normal app, nothing special (terminal)

Run: `python examples\bookstore\app.py`

> "This is a small bookstore API: a router, handlers, services, a cache and a database
> layer. It replays 400 requests. It's a normal Python program, and I'm not going to
> change a single line of it."

(Optional: flash the folder tree `api / services / domain / data`.)

## 0:55–1:20 · Beat 2: what callgraph records (terminal)

Run: `callgraph run examples\abc_demo.py`

> "Here's the idea on a 15-line script. `a` calls `b`, `b` calls `d`, then `a` calls `c`.
> callgraph hooks into Python's own runtime monitoring, records every call and return,
> and rebuilds the tree of what actually executed."

## 1:20–2:00 · Beat 3: real metrics in the terminal

Run: `callgraph run examples\bookstore\app.py --format stats`

> "Now the bookstore. 750 thousand function calls across 76 functions. Three things jump out:"

Point at each:

1. **Most called:** `normalize`, about 650,000 calls. "One tiny helper is 87% of all calls."
2. **Most time:** `Database._roundtrip`, about 65% of the run, at about 0.5ms each. "That's our I/O."
3. **Hottest path:** `dispatch → search → search_books → score → tokenize → normalize`.
   "Search re-tokenizes every book on every query. There's no index."

> "That's useful, but it's a table. Let's look at it."

## 2:00–3:40 · Beat 4: the dashboard (the wow moment, take your time here)

Run: `callgraph run examples\bookstore\app.py --format html --open`

1. **KPI row (5s):** "Calls, functions, time, and the three answers we just found, at the top."
2. **Call graph (25s):** "Every box is a function that actually ran, and the big number is
   how many times it was called. Colour tells you the same thing at a glance: green is
   called rarely, red is called the most. So your eye goes straight to `normalize`, 652
   thousand calls, the only red box. You're also looking at the architecture as it
   executed: router, handlers, services, down to the database. The dot is the module.
   Edges are real calls with counts, and the small 'med' value is each function's median time."
   (Tip: click a module in the legend to fade it out.)
3. **Click ▶ Replay execution (20s):** let it run. "This replays the run in the order it
   happened: the router, then each route, then down into the services. The counters are
   live call counts."
4. **Click `normalize` (15s):** "Click any function to get its numbers (650k calls,
   median about 50ns), who calls it, the duration distribution, and its source, right
   here. Metrics and code side by side."
5. **Click `Database.get_book` → follow 'Called by' to `Recommender.expand` (15s):**
   "And here's the second story. Recommendations walk 'similar books' recursively and hit the
   database once per book, the classic N+1 pattern. You can see it in the graph."
6. **Scroll to Execution pipeline (10s):** "This is the whole pipeline, every call path left to right
   in the order it first ran, with width proportional to time. Search is narrow by request count but wide by time."
7. **Rankings + Hot paths (10s):** switch the dropdown Most called → Self time → p95.

> "It's one HTML file with no server and no dependencies. You can attach it to a PR or a bug ticket."

## 3:40–4:15 · Beat 5: "does it slow my code down?" (address it before they ask)

Show the benchmark output (pre-run it, or cut it in from a recording, since it takes about 40s):

> "Every tracer has a cost, so here are real numbers. On this API, tracing everything costs about
> 2.5×. Scope it to the code you care about and it's **1.1×**, because on Python 3.12+ callgraph uses
> `sys.monitoring` and code you exclude is switched off entirely. The worst case is a tiny
> function called every 200 nanoseconds, which costs about 9×. And the timings you see
> are corrected: callgraph measures its own overhead at startup and subtracts it."

## 4:15–4:30 · Close + call to action

> "callgraph: what actually ran, in what order, how often, and how long. It's Python today,
> with more languages on the roadmap. Try it on a test suite or a slow script this week:
> `callgraph run your_script.py --format html --open`. Tell me what's confusing, what's
> missing, and where it's wrong."

---

## Live-demo variant (if presenting in person)

- Run `demo\run-demo.ps1` and press Enter between beats. Add `-Bench` only if you have a minute
  to spare, or show the pre-recorded bench numbers from a slide.
- If anything fails live, open `demo/output/bookstore-dashboard.html` directly. It is
  fully self-contained.
- Good live moment: ask the audience "which function do you think is called most?" before
  showing the stats.
