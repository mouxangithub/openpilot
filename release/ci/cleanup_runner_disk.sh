#!/usr/bin/env bash
# Free space on comma three GitHub Actions runner before/after CI builds.
# Usage: sudo ./release/ci/cleanup_runner_disk.sh [--aggressive]
set -euo pipefail

AGGRESSIVE=false
if [[ "${1:-}" == "--aggressive" ]]; then
  AGGRESSIVE=true
fi

RUNNER_ROOT="${RUNNER_ROOT:-/data/github/runner}"
BUILDS_ROOT="${BUILDS_ROOT:-/data/github/builds}"
BUILD_DIR="${BUILD_DIR:-/data/github/openpilot_build}"
MIN_FREE_MB="${MIN_FREE_MB:-2048}"

echo "==> 终止遗留 scons"
pkill -TERM -f '[s]cons' 2>/dev/null || true
sleep 2
pkill -KILL -f '[s]cons' 2>/dev/null || true

echo "==> 清理 runner 工作区与日志"
rm -rf "${RUNNER_ROOT}/_diag"/* 2>/dev/null || true
mkdir -p "${RUNNER_ROOT}/_diag"
find "${RUNNER_ROOT}/_work" -mindepth 1 -maxdepth 1 -mtime +1 -exec rm -rf {} + 2>/dev/null || true
rm -rf "${BUILDS_ROOT}/openpilot" "${BUILDS_ROOT}/_update" 2>/dev/null || true
rm -rf "${BUILDS_ROOT}/_temp"/* 2>/dev/null || true
rm -rf /data/github/tmp/* /tmp/test-checkout /tmp/op-bootstrap.* 2>/dev/null || true
find "${BUILD_DIR}" -mindepth 1 -delete 2>/dev/null || true

if $AGGRESSIVE; then
  echo "==> 激进模式：清理 scons 缓存"
  rm -rf /data/scons_cache/* /data/github/scons_cache/* 2>/dev/null || true
  find "${BUILDS_ROOT}" -mindepth 1 -maxdepth 1 -mtime +1 -exec rm -rf {} + 2>/dev/null || true
fi

free_mb="$(df -Pm /data | awk 'NR==2 {print $4}')"
echo "可用 /data: ${free_mb} MB (阈值 ${MIN_FREE_MB} MB)"
df -h /data /tmp
du -sh /data/github/* 2>/dev/null | sort -hr | head -10 || true

if [ "${free_mb:-0}" -lt "${MIN_FREE_MB}" ]; then
  echo "ERROR: /data 空间仍不足" >&2
  exit 1
fi

echo "==> 清理完成"
