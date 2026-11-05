#!/usr/bin/env bash
# Verify merge-conflict resolution is complete: no unmerged paths, no conflict
# markers in tracked files, and git's own conflict-marker check passes.
set -euo pipefail

FAILED=0

UNMERGED="$(git diff --name-only --diff-filter=U || true)"
if [ -n "${UNMERGED}" ]; then
  echo "::error::Unmerged paths remain:"
  echo "${UNMERGED}"
  FAILED=1
fi

MARKERS='^(<<<<<<<|=======$|>>>>>>>)'
while IFS= read -r file; do
  [ -n "${file}" ] || continue
  if [ -f "${file}" ] && grep -IlqE "${MARKERS}" "${file}" 2>/dev/null; then
    echo "::error::Conflict markers found in ${file}"
    grep -nE "${MARKERS}" "${file}" | head -5
    FAILED=1
  fi
done < <(git diff --name-only HEAD || true)

if ! git diff --check HEAD > /tmp/git_diff_check.log 2>&1; then
  echo "::error::git diff --check reported problems:"
  head -20 /tmp/git_diff_check.log
  FAILED=1
fi

exit "${FAILED}"
