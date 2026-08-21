#!/usr/bin/env bash
# op助手 卸载 — 停止 aid、删除 ai/ 目录，可选恢复 integrate 补丁
# 用法:
#   bash install/uninstall.sh
#   bash install/uninstall.sh --restore-integrate
#   curl -fsSL .../uninstall.sh | bash -s -- --yes
set -euo pipefail

RESTORE_INTEGRATE=0
KEEP_LOCAL_DATA=0
YES=0

usage() {
  cat <<'EOF'
op助手 卸载脚本

  uninstall.sh [选项]

选项:
  --root, -r PATH         openpilot 根目录（默认 /data/openpilot 或 OPENPILOT_ROOT）
  --restore-integrate     尝试用最新 .bak 恢复 params_keys.h / launch_chffrplus.sh
  --keep-local-data       删除前将 fork 分析/草稿备份到 <openpilot>/.op-ai-local-backup/
  --yes, -y               跳过确认提示
  --help, -h              显示帮助

说明:
  - 仅删除 <openpilot>/ai 目录并停止 ai.aid
  - Params 中的 ai_* 配置默认保留
  - 不指定 --restore-integrate 时，不会自动还原 launch / params_keys 补丁
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --restore-integrate) RESTORE_INTEGRATE=1; shift ;;
    --keep-local-data) KEEP_LOCAL_DATA=1; shift ;;
    --yes|-y) YES=1; shift ;;
    --root|-r) OPENPILOT_ROOT="$2"; shift 2 ;;
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
  if [[ -f "$script_dir/../../launch_chffrplus.sh" ]]; then
    echo "$(cd "$script_dir/../.." && pwd)"
    return 0
  fi
  echo "无法检测 OPENPILOT_ROOT。请设置: export OPENPILOT_ROOT=/path/to/openpilot" >&2
  exit 1
}

restore_latest_bak() {
  local file="$1"
  local dir base latest
  dir="$(dirname "$file")"
  base="$(basename "$file")"
  latest="$(ls -t "$dir/${base}.bak."* 2>/dev/null | head -1 || true)"
  if [[ -n "$latest" ]] && [[ -f "$latest" ]]; then
    cp -f "$latest" "$file"
    echo "已恢复: $file ← $(basename "$latest")"
    return 0
  fi
  echo "未找到备份，跳过: $file"
  return 1
}

ROOT="$(detect_openpilot_root)"
TARGET="$ROOT/ai"

echo "openpilot 根目录: $ROOT"
echo "op助手 路径:      $TARGET"

if [[ ! -d "$TARGET" ]]; then
  echo "未发现 $TARGET，无需卸载。"
  exit 0
fi

if [[ "$YES" -ne 1 ]]; then
  echo ""
  echo "将执行:"
  echo "  1. 停止 ai.aid 进程"
  if [[ "$KEEP_LOCAL_DATA" -eq 1 ]]; then
    echo "  2. 备份 ai/data/fork_* 到 $ROOT/.op-ai-local-backup/"
  fi
  echo "  3. 删除目录 $TARGET"
  if [[ "$RESTORE_INTEGRATE" -eq 1 ]]; then
    echo "  4. 尝试从 .bak 恢复 params_keys.h / launch_chffrplus.sh"
  fi
  echo ""
  echo "Params 中的 ai_* 配置不会删除。"
  read -r -p "确认卸载? [y/N] " ans
  case "$ans" in
    y|Y|yes|YES) ;;
    *) echo "已取消。"; exit 0 ;;
  esac
fi

echo "停止 ai.aid..."
pkill -f '[p]ython.* -m ai\.aid' 2>/dev/null || true
sleep 1

if [[ "$KEEP_LOCAL_DATA" -eq 1 ]]; then
  backup_root="$ROOT/.op-ai-local-backup"
  ts="$(date +%Y%m%d-%H%M%S)"
  dest="$backup_root/$ts"
  mkdir -p "$dest"
  for sub in fork_analysis fork_drafts; do
    if [[ -d "$TARGET/data/$sub" ]]; then
      cp -a "$TARGET/data/$sub" "$dest/"
      echo "已备份: data/$sub → $dest/$sub"
    fi
  done
fi

if [[ "$RESTORE_INTEGRATE" -eq 1 ]]; then
  for rel in common/params_keys.h openpilot/common/params_keys.h launch_chffrplus.sh; do
    f="$ROOT/$rel"
    if [[ -f "$f" ]]; then
      restore_latest_bak "$f" || true
    fi
  done
fi

echo "删除 $TARGET ..."
rm -rf "$TARGET"

echo ""
echo "=========================================="
echo " op助手 已卸载"
echo "  ai/ 目录已删除"
echo "  ai_* Params 仍保留（可重新安装后继续使用）"
if [[ "$RESTORE_INTEGRATE" -ne 1 ]]; then
  echo "  launch/params_keys 补丁未还原（可用 --restore-integrate）"
fi
echo "=========================================="
