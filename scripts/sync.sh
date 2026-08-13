#!/bin/bash
# Safe sync with origin for a repo whose bot commits data/ every 15 minutes.
# Usage: ./scripts/sync.sh   (then: git push)
#
# - Sets up the "keepours" merge driver (one-time, idempotent) so conflicts in
#   generated data/ files auto-resolve by keeping the local copy.
# - Pulls with merge; if anything in data/ still conflicts, resolves it and
#   completes the merge. Real conflicts (code/docs) stop for manual resolution.
set -e
cd "$(dirname "$0")/.."

git config merge.keepours.driver true

if ! git pull --no-rebase --no-edit; then
  conflicts=$(git diff --name-only --diff-filter=U)
  nondata=$(echo "$conflicts" | grep -v '^data/' || true)
  if [ -n "$nondata" ]; then
    echo "Manual resolution needed for non-generated files:"
    echo "$nondata"
    exit 1
  fi
  if [ -n "$conflicts" ]; then
    echo "$conflicts" | xargs git checkout --ours
    echo "$conflicts" | xargs git add
    git commit --no-edit
    echo "Auto-resolved generated data conflicts (kept local)."
  fi
fi
echo "In sync. Now: git push"
