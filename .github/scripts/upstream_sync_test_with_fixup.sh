#!/usr/bin/env bash
# Run a test command; on failure, hand the log to OpenCode for automatic fix
# attempts, then retry. Usage:
#   upstream_sync_test_with_fixup.sh '<test command>' <fix prompt file>
# Env: OPENCODE_API_KEY, OPENCODE_MODEL, MAX_FIX_ATTEMPTS (default 2),
#      SYNC_TEST_LOG (default $RUNNER_TEMP/upstream_test.log)
set -uo pipefail

TEST_CMD="${1:?usage: upstream_sync_test_with_fixup.sh <cmd> <prompt>}"
PROMPT_FILE="${2:-}"
MAX_FIX_ATTEMPTS="${MAX_FIX_ATTEMPTS:-2}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC_TEST_LOG="${SYNC_TEST_LOG:-${RUNNER_TEMP:-/tmp}/upstream_test.log}"
mkdir -p "$(dirname "${SYNC_TEST_LOG}")"

attempt=0
fixes_left="${MAX_FIX_ATTEMPTS}"
while :; do
  attempt=$((attempt + 1))
  echo ">> test attempt ${attempt}: ${TEST_CMD}"
  if bash -c "${TEST_CMD}" 2>&1 | tee "${SYNC_TEST_LOG}"; then
    echo ">> tests passed"
    exit 0
  fi
  echo ">> tests failed (attempt ${attempt}), log: ${SYNC_TEST_LOG}"

  if [ "${fixes_left}" -le 0 ]; then
    echo ">> no fix attempts left"
    exit 1
  fi
  fixes_left=$((fixes_left - 1))

  if [ ! -f "${SCRIPT_DIR}/upstream_sync_opencode_test_fix.sh" ]; then
    echo "::warning::fix helper missing; giving up"
    exit 1
  fi
  bash "${SCRIPT_DIR}/upstream_sync_opencode_test_fix.sh" "${SYNC_TEST_LOG}" "${PROMPT_FILE}" \
    || { echo ">> fix attempt failed to apply; giving up"; exit 1; }
done
