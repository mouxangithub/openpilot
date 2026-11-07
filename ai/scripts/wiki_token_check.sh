#!/usr/bin/env bash
# Validate WIKI_SYNC_TOKEN before wiki git push.
set -euo pipefail

TOKEN="${1:-${WIKI_SYNC_TOKEN:-}}"
REPO_SLUG="${2:-${GITHUB_REPOSITORY:-mouxangithub/ai}}"

if [[ -z "${TOKEN}" ]]; then
  echo "::error::WIKI_SYNC_TOKEN 为空"
  exit 1
fi

if [[ "${TOKEN}" == github_pat_* ]]; then
  echo "::error::检测到 fine-grained PAT (github_pat_*)，无法访问 ai.wiki 隐藏仓库。"
  echo "::error::请改用 classic PAT (ghp_开头)：Settings → Tokens → Generate new token (classic) → 勾选 repo → 选 All repositories"
  exit 1
fi

if [[ "${TOKEN}" != ghp_* && "${TOKEN}" != gho_* ]]; then
  echo "::warning::Token 不是常见的 ghp_/gho_ 格式，若仍失败请换 classic PAT"
fi

HTTP_USER="$(curl -sS -o /tmp/wiki_user.json -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/user)"
if [[ "${HTTP_USER}" != "200" ]]; then
  echo "::error::Token 无效或已过期 (GET /user → ${HTTP_USER})"
  exit 1
fi
LOGIN="$(python3 -c "import json; print(json.load(open('/tmp/wiki_user.json'))['login'])" 2>/dev/null || echo unknown)"
echo "Token 所属账号: ${LOGIN}"

SCOPES="$(curl -sSI -H "Authorization: Bearer ${TOKEN}" https://api.github.com/user | tr -d '\r' | awk -F': ' 'tolower($1)=="x-oauth-scopes"{print $2}')"
echo "OAuth scopes: ${SCOPES:-（fine-grained 或无 scope 头）}"
if [[ -n "${SCOPES}" && "${SCOPES}" != *repo* ]]; then
  echo "::error::classic PAT 未包含 repo scope，请重新生成并勾选 repo"
  exit 1
fi

OWNER="${REPO_SLUG%%/*}"
NAME="${REPO_SLUG##*/}"
WIKI_SLUG="${OWNER}/${NAME}.wiki"

HTTP_WIKI="$(curl -sS -o /tmp/wiki_repo.json -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${WIKI_SLUG}")"
echo "GET /repos/${WIKI_SLUG} → ${HTTP_WIKI}"
if [[ "${HTTP_WIKI}" == "404" ]]; then
  echo "::error::Token 看不到 wiki 仓库 ${WIKI_SLUG}。"
  echo "::error::常见原因：classic PAT 选了「Only select repositories」且只勾了 ${NAME}（不含 ${NAME}.wiki）。"
  echo "::error::解决：重新生成 classic PAT → repo → **All repositories**"
  exit 1
fi
if [[ "${HTTP_WIKI}" != "200" ]]; then
  echo "::error::无法访问 wiki 仓库 (HTTP ${HTTP_WIKI})"
  exit 1
fi

echo "Wiki 仓库 API 可达，可继续 git push。"
