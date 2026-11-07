#!/usr/bin/env bash
# op助手 git 更新（供 aid API 或手动调用）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/install.sh" --update "$@"
