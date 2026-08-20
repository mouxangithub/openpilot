#!/usr/bin/env bash
# Clone a git repo with China-friendly network tuning, optional proxy, and mirror fallbacks.
#
# Usage:
#   git_resilient_clone.sh <repo_url> <branch> <dest>
#
# Environment:
#   LOCAL_GIT_REFERENCE      e.g. /data/openpilot — shallow clone with --reference (C3 runner)
#   GITHUB_MIRROR_PREFIXES   comma-separated mirror URL prefixes (optional)
#   GITHUB_CLONE_FALLBACK_URLS  comma-separated full alternative repo URLs
#   GIT_CLONE_RETRIES          default 3
#   GIT_CLONE_RETRY_DELAY_SEC  default 15
#   GIT_CLONE_TIMEOUT_SEC      default 300

set -euo pipefail

REPO_URL="${1:?repo_url required}"
BRANCH="${2:?branch required}"
DEST="${3:?dest required}"

RETRIES="${GIT_CLONE_RETRIES:-3}"
DELAY="${GIT_CLONE_RETRY_DELAY_SEC:-15}"
TIMEOUT_SEC="${GIT_CLONE_TIMEOUT_SEC:-300}"
GITHUB_MIRROR_PREFIXES="${GITHUB_MIRROR_PREFIXES:-}"
LOCAL_GIT_REFERENCE="${LOCAL_GIT_REFERENCE:-}"

apply_git_network_tuning() {
  if [[ -n "$LOCAL_GIT_REFERENCE" && -d "$LOCAL_GIT_REFERENCE/.git" ]]; then
    git config --global --add safe.directory "$LOCAL_GIT_REFERENCE/.git" 2>/dev/null || true
  fi
  git config --global http.version HTTP/1.1
  git config --global http.postBuffer 524288000
  git config --global http.lowSpeedLimit 1000
  git config --global http.lowSpeedTime 120
  git config --global http.timeout 120
  git config --global core.compression 0

  if [[ -n "${GIT_HTTP_PROXY:-}" ]]; then
    git config --global http.proxy "$GIT_HTTP_PROXY"
  elif [[ -n "${ALL_PROXY:-}" ]]; then
    git config --global http.proxy "$ALL_PROXY"
  fi

  if [[ -n "${GIT_HTTPS_PROXY:-}" ]]; then
    git config --global https.proxy "$GIT_HTTPS_PROXY"
  elif [[ -n "${ALL_PROXY:-}" ]]; then
    git config --global https.proxy "$ALL_PROXY"
  fi
}

append_unique_url() {
  local url="$1"
  local existing
  [[ -z "$url" ]] && return 0
  for existing in "${CLONE_URLS[@]}"; do
    [[ "$existing" == "$url" ]] && return 0
  done
  CLONE_URLS+=("$url")
}

build_clone_urls() {
  CLONE_URLS=()
  append_unique_url "$REPO_URL"
  if [[ -n "${GITHUB_MIRROR_PREFIXES:-}" ]]; then
    IFS=',' read -ra prefixes <<< "$GITHUB_MIRROR_PREFIXES"
    for prefix in "${prefixes[@]}"; do
      prefix="${prefix// /}"
      [[ -z "$prefix" ]] && continue
      append_unique_url "${prefix}${REPO_URL}"
    done
  fi
  if [[ -n "${GITHUB_CLONE_FALLBACK_URLS:-}" ]]; then
    IFS=',' read -ra fallbacks <<< "$GITHUB_CLONE_FALLBACK_URLS"
    for fallback in "${fallbacks[@]}"; do
      fallback="${fallback// /}"
      append_unique_url "$fallback"
    done
  fi
}

try_clone() {
  local url="$1"
  local attempt
  local ref_args=()
  if [[ -n "$LOCAL_GIT_REFERENCE" && -d "$LOCAL_GIT_REFERENCE/.git" ]]; then
    ref_args=(--reference "$LOCAL_GIT_REFERENCE")
  fi
  rm -rf "$DEST"
  for ((attempt = 1; attempt <= RETRIES; attempt++)); do
    echo "Clone attempt ${attempt}/${RETRIES} from ${url}"
    if timeout "$TIMEOUT_SEC" git clone "${ref_args[@]}" --branch "$BRANCH" --single-branch --depth 1 "$url" "$DEST"; then
      return 0
    fi
    rm -rf "$DEST"
    if (( attempt < RETRIES )); then
      sleep $((attempt * DELAY))
    fi
  done
  return 1
}

try_local_mirror() {
  [[ -z "$LOCAL_GIT_REFERENCE" || ! -d "$LOCAL_GIT_REFERENCE/.git" ]] && return 1
  echo "::group::local git reference $LOCAL_GIT_REFERENCE"
  rm -rf "$DEST"
  if timeout "$TIMEOUT_SEC" git clone --reference "$LOCAL_GIT_REFERENCE" --dissociate \
      --branch "$BRANCH" --single-branch --depth 1 "$REPO_URL" "$DEST"; then
    echo "::endgroup::"
    echo "Clone succeeded via local reference (shallow)"
    return 0
  fi
  rm -rf "$DEST"
  echo "::endgroup::"
  return 1
}

apply_git_network_tuning
build_clone_urls

echo "Clone targets (${#CLONE_URLS[@]}):"
for url in "${CLONE_URLS[@]}"; do
  echo "  - $url"
done

if try_local_mirror; then
  exit 0
fi

for url in "${CLONE_URLS[@]}"; do
  echo "::group::git clone $url"
  if try_clone "$url"; then
    echo "::endgroup::"
    echo "Clone succeeded from $url"
    exit 0
  fi
  echo "::endgroup::"
  echo "::warning::Clone failed from $url, trying next source if available"
done

echo "::error::All clone sources failed for branch $BRANCH"
exit 1
