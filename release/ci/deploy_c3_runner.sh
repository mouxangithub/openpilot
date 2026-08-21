#!/usr/bin/env bash
# One-shot: install GitHub Actions runner + sync master-c3 on comma three.
# Usage (on C3, as root or with sudo):
#   curl -fsSL https://raw.githubusercontent.com/mouxangithub/openpilot/master-c3/release/ci/deploy_c3_runner.sh | bash -s -- <RUNNER_TOKEN>
# Or after git pull:
#   sudo ./release/ci/deploy_c3_runner.sh <RUNNER_TOKEN>
set -euo pipefail

TOKEN="${1:-}"
REPO_URL="${2:-https://github.com/mouxangithub/openpilot}"
OP_DIR="${OP_DIR:-/data/openpilot}"
BRANCH="${BRANCH:-master-c3}"

if [[ -z "$TOKEN" ]]; then
  echo "Usage: $0 <github_runner_registration_token> [repo_url]"
  echo "Get token: https://github.com/mouxangithub/openpilot/settings/actions/runners/new"
  exit 1
fi

if [[ ! -d "$OP_DIR/.git" ]]; then
  echo "ERROR: $OP_DIR is not a git repo"
  exit 1
fi

echo "==> Sync $BRANCH in $OP_DIR"
cd "$OP_DIR"
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
git submodule update --init --recursive panda opendbc_repo ai 2>/dev/null || \
  git submodule update --init --recursive

echo "==> Install GitHub Actions runner"
if [[ -x "$OP_DIR/release/ci/install_github_runner.sh" ]]; then
  "$OP_DIR/release/ci/install_github_runner.sh" --token "$TOKEN" --repo "$REPO_URL" --start-at-boot
else
  echo "ERROR: install_github_runner.sh not found"
  exit 1
fi

echo "==> Done. Check runner at: ${REPO_URL}/settings/actions/runners"
echo "    Prebuilt branch after CI: ${BRANCH}-prebuilt"
