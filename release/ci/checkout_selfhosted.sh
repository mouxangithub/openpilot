#!/usr/bin/env bash
# Checkout openpilot on self-hosted C3 runner via local git worktree (no network clone).
#
# Usage:
#   checkout_selfhosted.sh <branch> <workspace>
#
# Environment:
#   LOCAL_GIT_REPO      default /data/openpilot
#   GIT_REPO_OWNER      default comma (owner of the local bare/working repo)
#   RUNNER_USER         default github-runner
#   FETCH_TIMEOUT_SEC   default 45 — best-effort shallow fetch before worktree

set -euo pipefail

BRANCH="${1:?branch required}"
WORKSPACE="${2:?workspace required}"
LOCAL_REPO="${LOCAL_GIT_REPO:-/data/openpilot}"
REPO_OWNER="${GIT_REPO_OWNER:-comma}"
RUNNER_USER="${RUNNER_USER:-github-runner}"
FETCH_TIMEOUT="${FETCH_TIMEOUT_SEC:-45}"

log() { echo "[checkout_selfhosted] $*"; }

ensure_safe_directory() {
  local git_dir="$1"
  for user in "$REPO_OWNER" "$RUNNER_USER"; do
    sudo -u "$user" git config --global --add safe.directory "$git_dir" 2>/dev/null || true
  done
}

remove_workspace_worktree() {
  if ! sudo -u "$REPO_OWNER" git -C "$LOCAL_REPO" rev-parse --git-dir >/dev/null 2>&1; then
    return 0
  fi
  if sudo -u "$REPO_OWNER" git -C "$LOCAL_REPO" worktree list --porcelain 2>/dev/null | grep -q "^worktree $WORKSPACE$"; then
    log "Removing registered worktree at $WORKSPACE"
    sudo -u "$REPO_OWNER" git -C "$LOCAL_REPO" worktree remove -f "$WORKSPACE" || true
  fi
  if [[ -e "$WORKSPACE" ]]; then
    log "Removing workspace path $WORKSPACE"
    sudo rm -rf "$WORKSPACE"
  fi
}

prune_stale_worktrees() {
  local base="${LOCAL_REPO}/.ci-worktrees"
  [[ -d "$base" ]] || return 0
  find "$base" -mindepth 1 -maxdepth 1 -mtime +2 -exec rm -rf {} + 2>/dev/null || true
  sudo -u "$REPO_OWNER" git -C "$LOCAL_REPO" worktree prune 2>/dev/null || true
}

if ! sudo -u "$REPO_OWNER" git -C "$LOCAL_REPO" rev-parse --git-dir >/dev/null 2>&1; then
  echo "::error::Local git repo missing or unreadable at $LOCAL_REPO (runner must see /data/openpilot; do not bind-mount an empty dir over it)"
  exit 1
fi

ensure_safe_directory "$LOCAL_REPO"
ensure_safe_directory "$LOCAL_REPO/.git"

log "Local repo: $LOCAL_REPO branch: $BRANCH workspace: $WORKSPACE"

if timeout "$FETCH_TIMEOUT" sudo -u "$REPO_OWNER" git -C "$LOCAL_REPO" fetch --depth 1 origin "$BRANCH" 2>/dev/null; then
  log "Fetched latest $BRANCH from origin"
else
  echo "::warning::Could not fetch $BRANCH within ${FETCH_TIMEOUT}s; using local branch tip"
fi

remove_workspace_worktree
prune_stale_worktrees

mkdir -p "$(dirname "$WORKSPACE")"
sudo mkdir -p "$WORKSPACE" 2>/dev/null || true
sudo rm -rf "$WORKSPACE"
sudo mkdir -p "$(dirname "$WORKSPACE")"
sudo chown -R "${REPO_OWNER}:comma" "$(dirname "$WORKSPACE")" 2>/dev/null || true

log "Creating worktree (as $REPO_OWNER)..."
if ! sudo -u "$REPO_OWNER" git -C "$LOCAL_REPO" worktree add -f "$WORKSPACE" "$BRANCH"; then
  echo "::error::git worktree add failed for branch $BRANCH at $WORKSPACE"
  sudo -u "$REPO_OWNER" git -C "$LOCAL_REPO" worktree list || true
  exit 1
fi

sudo chown -R "${RUNNER_USER}:comma" "$WORKSPACE"
log "Worktree ready at $WORKSPACE"
sudo -u "$RUNNER_USER" git -C "$WORKSPACE" log -1 --oneline
