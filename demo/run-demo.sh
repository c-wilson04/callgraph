#!/usr/bin/env bash
# One-click callgraph demo (macOS / Linux / Git Bash).
#
#   ./demo/run-demo.sh              # step through, Enter between steps
#   ./demo/run-demo.sh --no-pause   # for recording
#   ./demo/run-demo.sh --bench      # also run the overhead benchmark
set -euo pipefail

NO_PAUSE=0
BENCH=0
for arg in "$@"; do
  case "$arg" in
    --no-pause) NO_PAUSE=1 ;;
    --bench) BENCH=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8

if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; BIN=.venv/Scripts
elif [ -x .venv/bin/python ]; then PY=.venv/bin/python; BIN=.venv/bin
else
  echo "Creating virtualenv (.venv) ..."
  python3 -m venv .venv 2>/dev/null || python -m venv .venv
  if [ -x .venv/bin/python ]; then PY=.venv/bin/python; BIN=.venv/bin; else PY=.venv/Scripts/python.exe; BIN=.venv/Scripts; fi
fi
"$PY" -m pip install --quiet --disable-pip-version-check -e ".[dev]"
CG="$BIN/callgraph"
mkdir -p demo/output

step() {
  printf '\n\033[90m%s\033[0m\n  \033[36m%s\033[0m\n' "$(printf '=%.0s' {1..78})" "$1"
  [ -n "${2:-}" ] && printf '  \033[33m> %s\033[0m\n' "$2"
  printf '\033[90m%s\033[0m\n' "$(printf '=%.0s' {1..78})"
}
pause() { [ "$NO_PAUSE" = 1 ] || read -r -p "  [Enter] to continue"; }

step "1. A normal Python app: a bookstore API replaying 400 requests" "python examples/bookstore/app.py"
"$PY" examples/bookstore/app.py
pause

step "2. callgraph records what ACTUALLY ran - no code changes, no decorators" "callgraph run examples/abc_demo.py"
sed 's/^/    /' examples/abc_demo.py
echo
"$CG" run examples/abc_demo.py
pause

step "3. Same app, traced: most-called functions, where time goes, hottest paths" "callgraph run examples/bookstore/app.py --format stats"
"$CG" run examples/bookstore/app.py --format stats --top 8
pause

OUT=demo/output/bookstore-dashboard.html
step "4. The interactive dashboard (single HTML file, works offline)" "callgraph run examples/bookstore/app.py --format html --open"
"$CG" run examples/bookstore/app.py --format html -o "$OUT" --open
echo "  Dashboard: $OUT"
pause

if [ "$BENCH" = 1 ]; then
  step "5a. Overhead, realistic service (simulated DB round-trips)" "callgraph bench examples/bookstore/app.py"
  "$CG" bench --repeat 3 examples/bookstore/app.py
  step "5b. Overhead when tracing is scoped (hot search module excluded)" "callgraph bench --exclude search.py examples/bookstore/app.py"
  "$CG" bench --repeat 3 --exclude search.py examples/bookstore/app.py
  step "5c. Worst case: pure CPU, a function call every ~200 ns" "callgraph bench examples/bookstore/app.py --no-latency"
  "$CG" bench --repeat 3 examples/bookstore/app.py --no-latency
fi

printf '\n\033[32mDemo complete.\033[0m\n'
