#!/usr/bin/env bash
# Sync ai/docs/wiki/*.md -> github.com/<owner>/<repo>.wiki
set -euo pipefail

COMMIT_MSG="${COMMIT_MSG:-docs: sync OP Agent wiki from ai/docs/wiki}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WIKI_SRC="$AI_ROOT/docs/wiki"
TMP="$(mktemp -d)"
SKIP_ON_MISSING="${WIKI_SYNC_SKIP_ON_MISSING:-0}"

cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

if [[ ! -d "$WIKI_SRC" ]]; then
  echo "Wiki source not found: $WIKI_SRC" >&2
  exit 1
fi

# Resolve owner/repo from GITHUB_REPOSITORY or WIKI_REPO URL.
resolve_repo() {
  if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
    echo "$GITHUB_REPOSITORY"
    return 0
  fi
  local url="${WIKI_REPO:-https://github.com/mouxangithub/ai.wiki.git}"
  if [[ "$url" =~ github\.com[:/]([^/]+)/([^/.]+) ]]; then
    echo "${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
    return 0
  fi
  return 1
}

wiki_git_url() {
  local slug="$1"
  local owner="${slug%%/*}"
  local repo="${slug##*/}"
  local token="${GITHUB_TOKEN:-${WIKI_SYNC_TOKEN:-}}"
  if [[ -n "$token" ]]; then
    echo "https://x-access-token:${token}@github.com/${owner}/${repo}.wiki.git"
  else
    echo "https://github.com/${owner}/${repo}.wiki.git"
  fi
}

api_token() {
  if [[ -n "${WIKI_SYNC_TOKEN:-}" ]]; then
    echo "$WIKI_SYNC_TOKEN"
  elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
    echo "$GITHUB_TOKEN"
  fi
}

enable_wiki_feature() {
  local slug="$1"
  local token
  token="$(api_token || true)"
  [[ -n "$token" ]] || return 1
  local code
  code="$(curl -sS -o /dev/null -w "%{http_code}" -X PATCH \
    -H "Authorization: Bearer ${token}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${slug}" \
    -d '{"has_wiki":true}')"
  [[ "$code" == "200" ]]
}

bootstrap_wiki_home() {
  local slug="$1"
  local token
  token="$(api_token || true)"
  [[ -n "$token" ]] || return 1
  local body
  body="$(printf '{"title":"Home","body":"OP Agent wiki — source: https://github.com/%s/tree/main/docs/wiki","format":"markdown"}' "$slug")"
  local code
  code="$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
    -H "Authorization: Bearer ${token}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${slug}/wiki/pages" \
    -d "$body")"
  [[ "$code" == "201" || "$code" == "200" || "$code" == "422" ]]
}

wiki_missing_help() {
  local slug="$1"
  cat >&2 <<EOF

GitHub Wiki git 仓库不存在: ${slug}.wiki

一次性修复（仓库管理员）:
  1. 打开 https://github.com/${slug}/settings
  2. Features → 勾选 Wikis → Save
  3. 重新运行: bash scripts/sync_github_wiki.sh
     或在 Actions 里手动触发 Sync GitHub Wiki

若 CI 的 GITHUB_TOKEN 无权改仓库设置，可添加 Secret WIKI_SYNC_TOKEN（classic PAT，repo 权限）。

源稿始终可在主仓浏览:
  https://github.com/${slug}/tree/main/docs/wiki
EOF
}

clone_wiki_repo() {
  local url="$1"
  if git clone "$url" "$TMP" 2>/dev/null; then
    return 0
  fi
  return 1
}

REPO_SLUG="$(resolve_repo)" || {
  echo "Cannot resolve GitHub repository (set GITHUB_REPOSITORY or WIKI_REPO)" >&2
  exit 1
}

WIKI_URL="$(wiki_git_url "$REPO_SLUG")"
MASKED_URL="https://github.com/${REPO_SLUG}.wiki.git"
echo "Cloning ${MASKED_URL}"

if ! clone_wiki_repo "$WIKI_URL"; then
  echo "Wiki clone failed; trying to enable Wikis + bootstrap Home page..."
  enable_wiki_feature "$REPO_SLUG" || true
  bootstrap_wiki_home "$REPO_SLUG" || true
  sleep 3
  if ! clone_wiki_repo "$WIKI_URL"; then
    wiki_missing_help "$REPO_SLUG"
    if [[ "$SKIP_ON_MISSING" == "1" || -n "${GITHUB_ACTIONS:-}" ]]; then
      echo "SKIP: Wiki not available; not failing the job."
      exit 0
    fi
    exit 2
  fi
fi

cp "$WIKI_SRC"/*.md "$TMP/"
cd "$TMP"
git add -A
if git diff --staged --quiet; then
  echo "Wiki already up to date."
  exit 0
fi
git -c user.name="${WIKI_GIT_USER_NAME:-github-actions[bot]}" \
    -c user.email="${WIKI_GIT_USER_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}" \
    commit -m "$COMMIT_MSG"
git push
echo "Wiki pushed successfully."
