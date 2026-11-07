#!/usr/bin/env bash
# Ask OpenCode to fix the failing test, applying its unified diff.
# Usage: upstream_sync_opencode_test_fix.sh <log_file> <prompt_file>
# Env: OPENCODE_API_KEY, OPENCODE_MODEL, OPENCODE_BASE_URL
set -euo pipefail

LOG_FILE="${1:?usage: upstream_sync_opencode_test_fix.sh <log> <prompt>}"
PROMPT_FILE="${2:-}"
OPENCODE_BASE_URL="${OPENCODE_BASE_URL:-https://api.opencode.ai/v1}"
OPENCODE_MODEL="${OPENCODE_MODEL:-opencode/deepseek-v4-flash}"

[ -n "${OPENCODE_API_KEY:-}" ] || { echo "OPENCODE_API_KEY not set"; exit 1; }
[ -f "${LOG_FILE}" ] || { echo "Log file missing: ${LOG_FILE}"; exit 1; }

SYSTEM_PROMPT=""
[ -n "${PROMPT_FILE}" ] && [ -f "${PROMPT_FILE}" ] && SYSTEM_PROMPT="$(cat "${PROMPT_FILE}")"

# Keep prompt bounded: last 400 lines of the log
LOG_TAIL="$(tail -400 "${LOG_FILE}")"
STATUS="$(git status --porcelain | head -50 || true)"

PAYLOAD="$(OC_SYSTEM_PROMPT="${SYSTEM_PROMPT}" LOG_TAIL="${LOG_TAIL}" STATUS="${STATUS}" OPENCODE_MODEL="${OPENCODE_MODEL}" python - <<'PYEOF'
import json, os
user = f"""Tests failed on a merged fork tree. Produce ONE unified diff (git format, paths relative to repo root) that fixes the failure. Do not weaken test assertions; prefer fixing product code. If the failure is caused by a genuine upstream behavior change that our fork must adopt, fix the fork side accordingly.

Git status:
{os.environ.get('STATUS', '')}

Failing log (tail):
{os.environ.get('LOG_TAIL', '')}

Return ONLY the diff, no prose, no markdown fences."""
msgs = []
sp = os.environ.get("OC_SYSTEM_PROMPT", "")
if sp:
    msgs.append({"role": "system", "content": sp})
msgs.append({"role": "user", "content": user})
print(json.dumps({"model": os.environ["OPENCODE_MODEL"], "messages": msgs, "temperature": 0.0}))
PYEOF
)"

RESPONSE="$(curl -sS --max-time 300 \
  -H "Authorization: Bearer ${OPENCODE_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" \
  "${OPENCODE_BASE_URL}/chat/completions")"

DIFF_TEXT="$(python - "${RESPONSE}" <<'PYEOF'
import json, re, sys
data = json.loads(sys.argv[1])
content = data["choices"][0]["message"]["content"]
# strip markdown fences if present
m = re.search(r"```(?:diff)?\s*\n(.*?)```", content, re.S)
text = m.group(1) if m else content
print(text.strip())
PYEOF
)"

[ -n "${DIFF_TEXT}" ] || { echo "OpenCode returned empty diff"; exit 1; }

printf '%s\n' "${DIFF_TEXT}" > /tmp/opencode_fix.diff
if git apply --check /tmp/opencode_fix.diff 2>/dev/null; then
  git apply /tmp/opencode_fix.diff
elif git apply --3way /tmp/opencode_fix.diff 2>/dev/null; then
  echo "Applied with 3way merge"
else
  echo "::error::OpenCode diff does not apply"; head -20 /tmp/opencode_fix.diff; exit 1
fi
echo "Fix patch applied."
