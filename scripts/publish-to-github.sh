#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${1:-callgraph}"
VISIBILITY="${2:-public}"

if ! /exec-daemon/gh auth status >/dev/null 2>&1; then
  echo "GitHub CLI is not authenticated."
  echo "Run: /exec-daemon/gh auth login --hostname github.com --git-protocol https"
  echo "Or set GH_TOKEN with repo scope and re-run this script."
  exit 1
fi

cd "$(dirname "$0")/.."

if /exec-daemon/gh repo view "$REPO_NAME" >/dev/null 2>&1; then
  echo "Repository $REPO_NAME already exists; pushing to it."
  REMOTE_URL="$(/exec-daemon/gh repo view "$REPO_NAME" --json url -q .url)"
else
  /exec-daemon/gh repo create "$REPO_NAME" --"$VISIBILITY" --source=. --remote=origin --description "Dynamic runtime call graph tracer for Python"
  REMOTE_URL="$(/exec-daemon/gh repo view "$REPO_NAME" --json url -q .url)"
fi

git push -u origin main
echo "Published to $REMOTE_URL"
