#!/usr/bin/env bash
# Resolve remaining merge conflicts with the OpenCode API (OpenAI-compatible).
# Usage: upstream_sync_opencode.sh <prompt_file>
# Env: OPENCODE_API_KEY, OPENCODE_MODEL, OPENCODE_BASE_URL (default https://api.opencode.ai/v1)
set -euo pipefail

PROMPT_FILE="${1:?usage: upstream_sync_opencode.sh <prompt_file>}"
OPENCODE_BASE_URL="${OPENCODE_BASE_URL:-https://api.opencode.ai/v1}"
OPENCODE_MODEL="${OPENCODE_MODEL:-opencode/deepseek-v4-flash}"

[ -n "${OPENCODE_API_KEY:-}" ] || { echo "::warning::OPENCODE_API_KEY not set; cannot auto-resolve conflicts"; exit 1; }
[ -f "${PROMPT_FILE}" ] || { echo "Prompt file ${PROMPT_FILE} missing"; exit 1; }

UNMERGED="$(git diff --name-only --diff-filter=U || true)"
[ -n "${UNMERGED}" ] || { echo "No unmerged files."; exit 0; }

SYSTEM_PROMPT="$(cat "${PROMPT_FILE}")"

opencode_complete() {
  local user_content="$1"
  local payload response
  # Build payload via python for correct JSON escaping
  payload="$(OC_SYSTEM_PROMPT="${SYSTEM_PROMPT}" OPENCODE_MODEL="${OPENCODE_MODEL}" python - "${user_content}" <<'PYEOF'
import json, os, sys
sys_prompt = os.environ.get("OC_SYSTEM_PROMPT", "")
user = sys.argv[1]
msgs = []
if sys_prompt:
    msgs.append({"role": "system", "content": sys_prompt})
msgs.append({"role": "user", "content": user})
print(json.dumps({"model": os.environ["OPENCODE_MODEL"], "messages": msgs, "temperature": 0.0}))
PYEOF
)"

  response="$(curl -sS --max-time 300 \
    -H "Authorization: Bearer ${OPENCODE_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "${payload}" \
    "${OPENCODE_BASE_URL}/chat/completions")"

  python - "${response}" <<'PYEOF'
import json, sys
data = json.loads(sys.argv[1])
try:
    print(data["choices"][0]["message"]["content"])
except (KeyError, IndexError):
    sys.stderr.write(f"Unexpected OpenCode response: {json.dumps(data)[:500]}\n")
    sys.exit(1)
PYEOF
}

while IFS= read -r file; do
  [ -n "${file}" ] || continue
  echo "Resolving conflicts in ${file} ..."
  [ -f "${file}" ] && file_content="$(cat "${file}")" || file_content="(file was deleted on one side; decide keep/delete)"
  user_content="Merge conflict in file: ${file}
${file_content}

Return ONLY the full resolved content of this file. No explanations, no markdown fences."
  OC_SYSTEM_PROMPT="${SYSTEM_PROMPT}" RESOLVED="$(opencode_complete "${user_content}")" || exit 1
  # Strip accidental markdown fences
  printf '%s\n' "${RESOLVED}" | sed -e '/^```/d' > "${file}"
  git add "${file}"
done <<< "${UNMERGED}"

echo "OpenCode conflict resolution finished."
