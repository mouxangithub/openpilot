#!/usr/bin/env bash
# Point tracked submodules at their own "master-c3-new" branches (child sync output).
# Submodules whose remote lacks the branch are left untouched with a warning.
set -euo pipefail

TARGET_BRANCH="${TARGET_BRANCH:-master-c3-new}"
FAILED=0

while read -r _sha _stage path; do
  [ -n "${path:-}" ] || continue
  if ! git -C "${path}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "::warning::submodule ${path} not initialized; skipping"
    continue
  fi
  if git -C "${path}" ls-remote --exit-code --heads origin "${TARGET_BRANCH}" >/dev/null 2>&1; then
    echo "Updating submodule ${path} -> origin/${TARGET_BRANCH}"
    git -C "${path}" fetch origin "${TARGET_BRANCH}"
    git -C "${path}" checkout -B "${TARGET_BRANCH}" "origin/${TARGET_BRANCH}"
    git add "${path}"
  else
    echo "::warning::submodule ${path} has no ${TARGET_BRANCH} branch; leaving pointer unchanged"
  fi
done < <(git submodule status)

exit "${FAILED}"
