#!/usr/bin/env bash
# Fast, dependency-light validation of the merged tree (no scons build).
# 1. byte-compile every python file touched by the merge
# 2. run cereal unit tests + repo CI gates (schema guard, artifacts lint)
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

FAILED=0

# --- 1. compile check on touched python files -------------------------------
TOUCHED_PY="$(git diff --name-only origin/"${FORK_BRANCH:-master-c3}"..HEAD -- '*.py' || true)"
if [ -n "${TOUCHED_PY}" ]; then
  echo "${TOUCHED_PY}" | tr '\n' '\0' | xargs -0 -r python -m py_compile || FAILED=1
fi

# --- 2. minimal test deps ----------------------------------------------------
if ! python -c "import pytest" 2>/dev/null; then
  python -m pip install -q pytest pytest-timeout || { echo "::warning::pytest unavailable, skipping unit tests"; exit "${FAILED}"; }
fi

# --- 3. repo CI gates (skip silently if the tool is not present) -------------
for gate in \
  tools/ci/check_capnp_schema.py \
  tools/ci/check_validation_artifacts.py \
  tools/ci/check_upstream_sync_json.py; do
  if [ -f "${gate}" ]; then
    echo ">> gate: ${gate}"
    python "${gate}" || FAILED=1
  fi
done

# --- 4. cereal unit tests ----------------------------------------------------
if [ -d "${ROOT}/cereal" ]; then
  echo ">> pytest cereal/"
  python -m pytest cereal/test -q -x --timeout=120 || FAILED=1
elif [ -d "${ROOT}/opendbc_repo/opendbc/safety/tests" ]; then
  echo ">> pytest opendbc safety tests (py only)"
  python -m pytest opendbc_repo/opendbc/safety/tests/test_common.py -q --timeout=120 || FAILED=1
fi

exit "${FAILED}"
