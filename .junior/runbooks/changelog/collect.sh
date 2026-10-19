#!/bin/sh
# Commits on this branch (vs main, or $BASE) + the current Unreleased section,
# so the model drafts only what's missing.
set -eu
cd "$JUNIOR_PROJECT_DIR"
base="${BASE:-main}"
echo "## Commits ($base..HEAD)"
git log --reverse --format='### %s%n%n%b' "$base..HEAD"
echo "## Files changed"
git diff --stat "$base...HEAD"
echo "## CHANGELOG.md (top)"
sed -n '1,40p' CHANGELOG.md
