#!/usr/bin/env bash
# op助手（op AI Agent）一键安装 — 安装到 $OPENPILOT_ROOT/ai
# 用法:
#   curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
#   curl -fsSL ... | bash -s -- --root /path/to/openpilot
#   bash install/install.sh --update
set -euo pipefail

AI_REPO_SSH="${AI_REPO:-git@github.com:mouxangithub/ai.git}"
AI_REPO_HTTPS="${AI_REPO_HTTPS:-https://github.com/mouxangithub/ai.git}"
AI_BRANCH="${AI_BRANCH:-main}"
UPDATE_ONLY=0

usage() {
  cat <<'EOF'
op助手 安装脚本

  install.sh [选项]

选项:
  --root, -r PATH    openpilot 根目录（默认: /data/openpilot 或 OPENPILOT_ROOT）
  --update, -u       仅更新已 git 安装的 ai/ 目录
  --branch BRANCH    跟踪分支（默认 main）
  --help, -h         显示帮助

环境变量:
  OPENPILOT_ROOT     同 --root
  AI_REPO            SSH 克隆地址
  AI_REPO_HTTPS      HTTPS 克隆地址（SSH 不可用时）

示例（车机 C2/C3/C4）:
  curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
  # C2（comma two / dragonpilot d2 等 Android 宿主）同样使用 /data/openpilot

示例（PC）:
  export OPENPILOT_ROOT=~/openpilot
  curl -fsSL https://raw.githubusercontent.com/mouxangithub/ai/main/install/install.sh | bash
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --update|-u) UPDATE_ONLY=1; shift ;;
    --root|-r) OPENPILOT_ROOT="$2"; shift 2 ;;
    --branch) AI_BRANCH="$2"; shift 2 ;;
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
  # 从 install 脚本位置推断（开发树内 ai/install/install.sh）
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
      echo "$AI_REPO_SSH"
      return 0
    fi
  fi
  echo "$AI_REPO_HTTPS"
}

ROOT="$(detect_openpilot_root)"
TARGET="$ROOT/ai"
GIT_URL="$(pick_git_url)"

echo "openpilot 根目录: $ROOT"
echo "op助手 目标路径:  $TARGET"
echo "Git 远程:         $GIT_URL (branch $AI_BRANCH)"

do_update() {
  cd "$TARGET"
  git fetch origin "$AI_BRANCH"
  git checkout "$AI_BRANCH" 2>/dev/null || git checkout -B "$AI_BRANCH" "origin/$AI_BRANCH"
  git pull --ff-only origin "$AI_BRANCH"
  local ver commit
  ver="$(cat VERSION 2>/dev/null || echo unknown)"
  commit="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "已更新 op助手 VERSION=$ver commit=$commit"
}

do_clone() {
  if [[ -d "$TARGET" ]]; then
    if [[ -d "$TARGET/.git" ]]; then
      echo "检测到已有 git 安装的 ai/ → 执行更新（git pull）"
      do_update
      return 0
    fi
    local bak="${TARGET}.bak.$(date +%s)"
    echo "检测到已有 ai/ 目录（非 git）→ 备份后重新克隆"
    echo "  $TARGET -> $bak"
    mv "$TARGET" "$bak"
  fi
  echo "克隆 op助手..."
  git clone --depth 1 -b "$AI_BRANCH" "$GIT_URL" "$TARGET"
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
    echo ">>> 集成 openpilot（launch + 可选 SpDevBeep；扫描 fork/设备并写入 workspace 快照）"
    OPENPILOT_ROOT="$ROOT" PYTHONPATH="$ROOT" "$py" "$integrate" --root "$ROOT" --skip-compile || {
      echo "警告: openpilot 集成未完全成功，见上方日志。" >&2
    }
  fi
}
run_integrate

seed_workspace() {
  local py=python3
  command -v "$py" >/dev/null 2>&1 || py=python
  echo ""
  echo ">>> 初始化 op助手 workspace（ai/workspace/）"
  OPENPILOT_ROOT="$ROOT" PYTHONPATH="$ROOT:$TARGET" "$py" -c \
    "from ai.core.wspace.store import ensure_default_workspace_files; ensure_default_workspace_files(); print('workspace ready:', __import__('ai.core.wspace.store', fromlist=['workspace_dir']).workspace_dir())" \
    || echo "警告: workspace 初始化失败，首次启动 aid 时会重试。" >&2
}
seed_workspace

OP_BIN="$TARGET/scripts/op"
if [[ -x "$OP_BIN" ]] || [[ -f "$OP_BIN" ]]; then
  chmod +x "$OP_BIN" 2>/dev/null || true
  if [[ -d "$ROOT/.git" ]] && [[ -w "$ROOT" ]]; then
    ln -sf "$OP_BIN" "$ROOT/op" 2>/dev/null || cp "$OP_BIN" "$ROOT/op" 2>/dev/null || true
    chmod +x "$ROOT/op" 2>/dev/null || true
    echo "已安装 CLI: $ROOT/op"
  fi
fi

VER="$(cat "$TARGET/VERSION" 2>/dev/null || echo unknown)"
echo ""
echo "=========================================="
echo " op助手 安装完成"
echo "  路径:    $TARGET"
echo "  版本:    $VER"
echo "  启动:    cd $ROOT && python3 -m ai.aid"
echo "  CLI:     $TARGET/scripts/op  (或: python3 -m ai.cli)"
echo "  Web UI:  http://<设备IP>:5090"
echo "=========================================="
echo ""
echo "下一步:"
echo "  1. 若集成成功，重启 openpilot 或手动: cd $ROOT && python3 -m ai.aid"
echo "  2. 浏览器打开 :5090 → 首次配置向导 / 设置 → 模型 API"
echo "  3. 开发面板: 设置 → 开发 → 版本 / Fork 同步"
echo ""
