<#
.SYNOPSIS
  One-click callgraph demo (Windows PowerShell 5.1+ / PowerShell 7).

.DESCRIPTION
  Sets up a virtualenv if needed, then walks through the demo beats:
    1. the sample app runs normally
    2. the call tree of a tiny script (what callgraph records)
    3. terminal metrics for the bookstore API
    4. the interactive dashboard (opens in your browser)
    5. (optional, -Bench) tracing overhead benchmark

.PARAMETER NoPause
  Don't wait for Enter between steps (use when recording a video).

.PARAMETER Bench
  Also run the overhead benchmark (about 30-60 seconds).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File demo\run-demo.ps1
  powershell -ExecutionPolicy Bypass -File demo\run-demo.ps1 -NoPause -Bench
#>
param(
    [switch]$NoPause,
    [switch]$Bench
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo
$env:PYTHONIOENCODING = "utf-8"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Step([string]$Title, [string]$Command) {
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor DarkGray
    Write-Host "  $Title" -ForegroundColor Cyan
    if ($Command) { Write-Host "  > $Command" -ForegroundColor Yellow }
    Write-Host ("=" * 78) -ForegroundColor DarkGray
}

function Pause-Demo {
    if (-not $NoPause) { [void](Read-Host "  [Enter] to continue") }
}

# --- setup --------------------------------------------------------------------------
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "Creating virtualenv (.venv) ..." -ForegroundColor DarkGray
    $base = (Get-Command py -ErrorAction SilentlyContinue)
    if ($base) { & py -3 -m venv .venv } else { & python -m venv .venv }
}
& $Py -m pip install --quiet --disable-pip-version-check -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
$CG = Join-Path $Repo ".venv\Scripts\callgraph.exe"
New-Item -ItemType Directory -Force (Join-Path $Repo "demo\output") | Out-Null
# callgraph prints status lines on stderr; never treat those as fatal.
$ErrorActionPreference = "Continue"

# --- 1. the app, untouched ----------------------------------------------------------
Step "1. A normal Python app: a bookstore API replaying 400 requests" "python examples\bookstore\app.py"
& $Py examples\bookstore\app.py
Pause-Demo

# --- 2. what callgraph records ------------------------------------------------------
Step "2. callgraph records what ACTUALLY ran - no code changes, no decorators" "callgraph run examples\abc_demo.py"
Get-Content examples\abc_demo.py | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
Write-Host ""
& $CG run examples\abc_demo.py
Pause-Demo

# --- 3. metrics in the terminal -----------------------------------------------------
Step "3. Same app, traced: most-called functions, where time goes, hottest paths" "callgraph run examples\bookstore\app.py --format stats"
& $CG run examples\bookstore\app.py --format stats --top 8
Pause-Demo

# --- 4. dashboard -------------------------------------------------------------------
$Out = "demo\output\bookstore-dashboard.html"
Step "4. The interactive dashboard (single HTML file, works offline)" "callgraph run examples\bookstore\app.py --format html --open"
& $CG run examples\bookstore\app.py --format html -o $Out --open
Write-Host "  Dashboard: $(Resolve-Path $Out)" -ForegroundColor Green
Pause-Demo

# --- 5. overhead --------------------------------------------------------------------
if ($Bench) {
    Step "5a. Overhead, realistic service (simulated DB round-trips)" "callgraph bench examples\bookstore\app.py"
    & $CG bench --repeat 3 examples\bookstore\app.py
    Step "5b. Overhead when tracing is scoped (hot search module excluded)" "callgraph bench --exclude search.py examples\bookstore\app.py"
    & $CG bench --repeat 3 --exclude search.py examples\bookstore\app.py
    Step "5c. Worst case: pure CPU, a function call every ~200 ns" "callgraph bench examples\bookstore\app.py --no-latency"
    & $CG bench --repeat 3 examples\bookstore\app.py --no-latency
}

Write-Host ""
Write-Host "Demo complete." -ForegroundColor Green
