#!/usr/bin/env bash
# op Web UI 一键安装 — 安装到 $OPENPILOT_ROOT/webui（与 ai/ 并行）
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/mouxangithub/webui/main/install/install.sh | bash
#   bash install/install.sh --root /path/to/openpilot
set -euo pipefail

WEBUI_REPO_SSH="${WEBUI_REPO:-git@github.com:mouxangithub/webui.git}"
WEBUI_REPO_HTTPS="${WEBUI_REPO_HTTPS:-https://github.com/mouxangithub/webui.git}"
WEBUI_BRANCH="${WEBUI_BRANCH:-main}"
UPDATE_ONLY=0

usage() {
  cat <<'EOF'
op Web UI 安装脚本

  install.sh [选项]

选项:
  --root, -r PATH    openpilot 根目录（默认: /data/openpilot 或 OPENPILOT_ROOT）
  --update, -u       仅更新已 git 安装的 webui/ 目录
  --branch BRANCH    跟踪分支（默认 main）
  --help, -h         显示帮助

环境变量:
  OPENPILOT_ROOT     同 --root
  WEBUI_REPO         SSH 克隆地址
  WEBUI_REPO_HTTPS   HTTPS 克隆地址

示例（车机）:
  curl -fsSL https://raw.githubusercontent.com/mouxangithub/webui/main/install/install.sh | bash

示例（PC 开发）:
  export OPENPILOT_ROOT=~/openpilot
  curl -fsSL https://raw.githubusercontent.com/mouxangithub/webui/main/install/install.sh | bash
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --update|-u) UPDATE_ONLY=1; shift ;;
    --root|-r) OPENPILOT_ROOT="$2"; shift 2 ;;
    --branch) WEBUI_BRANCH="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage; exit 1 ;;
  esac
done

detect_openpilot_root() {
  if [[ -n "${OPENPILOT_ROOT:-}" ]] && [[ -d "$OPENPILOT_ROOT" ]]; then
    echo "$OPENPILOT_ROOT"
    return 0
  fi
  if [[ -d "/data/openpilot" ]]; then
    echo "/data/openpilot"
    return 0
  fi
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -f "$script_dir/../../launch_chffrplus.sh" ]] || [[ -f "$script_dir/../../launch_openpilot.sh" ]]; then
    echo "$(cd "$script_dir/../.." && pwd)"
    return 0
  fi
  echo "无法检测 OPENPILOT_ROOT。请设置: export OPENPILOT_ROOT=/path/to/openpilot" >&2
  exit 1
}

pick_git_url() {
  if command -v ssh >/dev/null 2>&1; then
    if ssh -o BatchMode=yes -o ConnectTimeout=8 -T git@github.com 2>&1 | grep -qi "successfully authenticated"; then
      echo "$WEBUI_REPO_SSH"
      return 0
    fi
  fi
  echo "$WEBUI_REPO_HTTPS"
}

ROOT="$(detect_openpilot_root)"
TARGET="$ROOT/webui"
GIT_URL="$(pick_git_url)"

echo "openpilot 根目录: $ROOT"
echo "Web UI 目标路径:  $TARGET"
echo "Git 远程:         $GIT_URL (branch $WEBUI_BRANCH)"

do_update() {
  cd "$TARGET"
  git fetch origin "$WEBUI_BRANCH"
  git checkout "$WEBUI_BRANCH" 2>/dev/null || git checkout -B "$WEBUI_BRANCH" "origin/$WEBUI_BRANCH"
  git pull --ff-only origin "$WEBUI_BRANCH"
  local ver commit
  ver="$(cat VERSION 2>/dev/null || echo unknown)"
  commit="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "已更新 Web UI VERSION=$ver commit=$commit"
}

do_clone() {
  if [[ -d "$TARGET" ]]; then
    if [[ -d "$TARGET/.git" ]]; then
      echo "检测到已有 git 安装的 webui/ → 执行更新（git pull）"
      do_update
      return 0
    fi
    local bak="${TARGET}.bak.$(date +%s)"
    echo "检测到已有 webui/ 目录（非 git）→ 备份后重新克隆"
    echo "  $TARGET -> $bak"
    mv "$TARGET" "$bak"
  fi
  echo "克隆 op Web UI..."
  git clone --depth 1 -b "$WEBUI_BRANCH" "$GIT_URL" "$TARGET"
}

if [[ "$UPDATE_ONLY" -eq 1 ]]; then
  if [[ ! -d "$TARGET/.git" ]]; then
    echo "错误: $TARGET 不是 git 安装，请直接运行 install.sh 进行首次安装。" >&2
    exit 1
  fi
  do_update
else
  do_clone
fi

run_integrate() {
  local py=python3
  command -v "$py" >/dev/null 2>&1 || py=python
  local integrate="$TARGET/install/integrate_openpilot.py"
  if [[ -f "$integrate" ]]; then
    echo ""
    echo ">>> 集成 openpilot（launch_chffrplus.sh 自启动 webuid :5080）"
    OPENPILOT_ROOT="$ROOT" PYTHONPATH="$ROOT" "$py" "$integrate" --root "$ROOT" || {
      echo "警告: launch 集成未完全成功，见上方日志。" >&2
    }
  fi
}
run_integrate

ver="$(cat "$TARGET/VERSION" 2>/dev/null || echo unknown)"
echo ""
echo "=========================================="
echo "  op Web UI 安装完成"
echo "  版本: $ver"
echo "  Web:  https://<设备IP>:5080/  (车机 TLS；无屏 USB 共享: https://10.255.128.121:5080/)"
echo "  手动: cd $ROOT && PYTHONPATH=$ROOT WEBUI_TLS=1 python3 -m webui.webuid"
echo "  说明: 与 ai 相同，首次启动会自动安装 aiohttp 到 \$OPENPILOT_ROOT/.pydeps"
echo "=========================================="
