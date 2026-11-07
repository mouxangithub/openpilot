#!/usr/bin/env bash
# Open a draft PR from OUTPUT_BRANCH -> FORK_BRANCH.
# Usage: upstream_sync_open_pr.sh "<PR title>"
# Env: GH_TOKEN (required), FORK_BRANCH, OUTPUT_BRANCH, UPSTREAM_HEAD,
#      SYNC_TEST_PASSED ("true"/"false"), SYNC_TEST_LOG, OPEN_PR_EXTRA_BODY
set -euo pipefail

TITLE="${1:?usage: upstream_sync_open_pr.sh <title>}"
FORK_BRANCH="${FORK_BRANCH:?FORK_BRANCH not set}"
OUTPUT_BRANCH="${OUTPUT_BRANCH:?OUTPUT_BRANCH not set}"

command -v gh >/dev/null 2>&1 || { echo "::error::gh CLI not available"; exit 1; }
export GH_TOKEN="${GH_TOKEN:?GH_TOKEN not set}"

if [ -f "${SYNC_TEST_LOG:-}" ]; then
  TEST_LOG_TAIL="$(tail -60 "${SYNC_TEST_LOG}")"
else
  TEST_LOG_TAIL="(test log unavailable)"
fi
if [ "${SYNC_TEST_PASSED:-false}" = "true" ]; then
  TEST_SECTION="✅ 自动验证通过（仅限静态/单测门禁，不构成上车资格）"
else
  TEST_SECTION="⚠️ 自动验证未通过或被跳过，需人工复核"
fi

BODY="$(cat <<EOF
## 上游自动同步

- upstream commit: \`${UPSTREAM_HEAD:-unknown}\`
- head: \`${OUTPUT_BRANCH}\` → base: \`${FORK_BRANCH}\`
- 验证状态: ${TEST_SECTION}

<details><summary>测试日志（尾部）</summary>

\`\`\`
${TEST_LOG_TAIL}
\`\`\`

</details>

${OPEN_PR_EXTRA_BODY:-}

> 注：本 PR 由自动化生成，merge 前必须人工复核冲突解决与测试结果。
EOF
)"

# Existing open PR for this head/base? Update instead of failing.
EXISTING="$(gh pr list --head "${OUTPUT_BRANCH}" --base "${FORK_BRANCH}" --state open --json number --jq '.[0].number' 2>/dev/null || true)"
if [ -n "${EXISTING}" ]; then
  gh pr edit "${EXISTING}" --title "${TITLE}" --body "${BODY}"
  echo "Updated existing PR #${EXISTING}"
else
  gh pr create --draft --base "${FORK_BRANCH}" --head "${OUTPUT_BRANCH}" \
    --title "${TITLE}" --body "${BODY}"
fi
