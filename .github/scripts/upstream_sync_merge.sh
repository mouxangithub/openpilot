#!/usr/bin/env bash
# Merge upstream (sunnypilot master) into our fork branch, producing OUTPUT_BRANCH.
# Outputs (GITHUB_OUTPUT):
#   merge_conflicts=true|false
#   upstream_head=<sha>
# Never hard-fails on conflicts; later steps resolve them.
set -euo pipefail

FORK_BRANCH="${FORK_BRANCH:?FORK_BRANCH not set}"
OUTPUT_BRANCH="${OUTPUT_BRANCH:?OUTPUT_BRANCH not set}"
UPSTREAM_URL="${UPSTREAM_URL:?UPSTREAM_URL not set}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-master}"

git config user.name "GitHub Actions Bot"
git config user.email "<>"

git fetch origin "${FORK_BRANCH}"
git checkout -B "${OUTPUT_BRANCH}" "origin/${FORK_BRANCH}"

if git remote get-url upstream >/dev/null 2>&1; then
  git remote set-url upstream "${UPSTREAM_URL}"
else
  git remote add upstream "${UPSTREAM_URL}"
fi
git fetch upstream "${UPSTREAM_BRANCH}" --tags

UPSTREAM_HEAD="$(git rev-parse "upstream/${UPSTREAM_BRANCH}")"
echo "upstream_head=${UPSTREAM_HEAD}" >> "${GITHUB_OUTPUT:-/dev/stdout}"

if git merge-base --is-ancestor "${UPSTREAM_HEAD}" HEAD; then
  echo "Upstream ${UPSTREAM_HEAD} already merged; nothing to do."
  echo "merge_conflicts=false" >> "${GITHUB_OUTPUT:-/dev/stdout}"
  exit 0
fi

MERGE_LOG="$(mktemp)"
if git merge "upstream/${UPSTREAM_BRANCH}" --no-edit --no-ff >"${MERGE_LOG}" 2>&1; then
  echo "merge_conflicts=false" >> "${GITHUB_OUTPUT:-/dev/stdout}"
  tail -5 "${MERGE_LOG}"
else
  cat "${MERGE_LOG}"
  echo "merge_conflicts=true" >> "${GITHUB_OUTPUT:-/dev/stdout}"
  exit 0
fi
