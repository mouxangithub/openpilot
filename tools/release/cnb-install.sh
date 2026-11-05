#!/usr/bin/env bash
# Git 一键安装/重装脚本 —— 绕过 AGNOS 安装器 UI，直接从 git 仓库安装。
#
# 原理：等价于官方 installer.cc 的安装流程
#   git clone <仓库> -b <分支> --depth=1 /data/tmppilot
#   → 校验 → 替换 /data/openpilot → 写 /data/continue.sh → 重启 openpilot
#
# 支持两个源（SOURCE 环境变量或第一个参数）：
#   cnb    (默认) https://cnb.cool/mouxancnb/openpilot.git  分支 staging
#          国内 CDN 直连，精简发布树（无 submodule/LFS），推荐国内用户。
#   github         https://github.com/mouxangithub/openpilot.git 分支 test
#          完整源码树：自动 --recurse-submodules + git lfs pull
#          （updater zipapp 本身是 LFS 文件，必须拉取；800MB 的
#          big_driving_tinygrad.pkl 默认跳过，与 CI 打包口径一致）。
#          国内直连 GitHub 较慢，submodule/LFS 可能失败，需网络质量好。
#
# 用法（PC 上执行）：
#   ssh comma@<设备IP> "bash -s" < tools/release/cnb-install.sh
#   ssh comma@<设备IP> "SOURCE=github bash -s" < tools/release/cnb-install.sh
#   ssh comma@<设备IP> "SOURCE=github BRANCH=dev bash -s" < tools/release/cnb-install.sh
# 或设备上直接：
#   bash tools/release/cnb-install.sh [cnb|github]
#
# 自举 URL（打包分支自举重装）：
#   CNB:    https://cnb.cool/mouxancnb/openpilot/-/git/raw/staging/tools/release/cnb-install.sh
#   GitHub: https://raw.githubusercontent.com/mouxangithub/openpilot/test/tools/release/cnb-install.sh
#
# 可覆盖变量：REPO_URL / BRANCH / SOURCE

SOURCE="${1:-${SOURCE:-cnb}}"
case "$SOURCE" in
  cnb)
    REPO_URL="${REPO_URL:-https://cnb.cool/mouxancnb/openpilot.git}"
    BRANCH="${BRANCH:-staging}"
    STRIPPED=1
    ;;
  github)
    REPO_URL="${REPO_URL:-https://github.com/mouxangithub/openpilot.git}"
    BRANCH="${BRANCH:-test}"
    STRIPPED=0
    ;;
  *)
    echo "错误：未知源 '$SOURCE'（可选 cnb | github）" >&2
    exit 1
    ;;
esac

INSTALL_PATH=/data/openpilot
TMP_PATH=/data/tmppilot
CONTINUE=/data/continue.sh
BACKUP=/data/safe_staging/old_openpilot_cnb_install
MIN_TIME=1735689600   # 2025-01-01，时钟早于它视为无效（git/TLS 会失败）
# 源码树安装所需最小空间（源码+submodules+LFS 模型，不含 800MB big 模型）
MIN_AVAIL_KB=$([ "$STRIPPED" = "1" ] && echo 5242880 || echo 8388608)

set -u

echo "==> [1/6] 检查运行环境（源=$SOURCE 分支=$BRANCH）"
if [ "$(id -u)" = "0" ]; then
  echo "错误：请以 comma 用户运行（不要用 sudo bash）" >&2
  exit 1
fi
AVAIL_KB=$(df -Pk /data | awk 'NR==2 {print $4}')
echo "    /data 可用空间: $((AVAIL_KB / 1024)) MB"
if [ "$AVAIL_KB" -lt "$MIN_AVAIL_KB" ]; then
  echo "错误：/data 可用空间不足 $((MIN_AVAIL_KB / 1048576))GB，先清理旧安装（/data/safe_staging/）" >&2
  exit 1
fi

echo "==> [2/6] 停止 openpilot"
sudo systemctl stop comma.service 2>/dev/null || true
tmux kill-session -t comma 2>/dev/null || true
pkill -f launch_chffrplus 2>/dev/null || true
pkill -f launch_openpilot 2>/dev/null || true
pkill -f 'python3.*manager.py' 2>/dev/null || true
sleep 2
echo "    已停止"

echo "==> [3/6] 等待系统时钟就绪"
for _ in $(seq 1 30); do
  [ "$(date +%s)" -ge "$MIN_TIME" ] && break
  sleep 2
done
if [ "$(date +%s)" -lt "$MIN_TIME" ]; then
  # 无 NTP 设备从 HTTP 响应头校时（两个源各试一次，国内优先 CNB）
  for host in https://cnb.cool https://github.com; do
    HTTP_DATE=$(curl -fsSI "$host" 2>/dev/null | grep -i '^date:' | cut -d' ' -f2- | tr -d '\r')
    if [ -n "$HTTP_DATE" ]; then
      echo "    从 $host 校时: $HTTP_DATE"
      sudo date -s "$HTTP_DATE" >/dev/null 2>&1 && break
    fi
  done
fi
if [ "$(date +%s)" -lt "$MIN_TIME" ]; then
  echo "错误：系统时钟无效且校时失败，git TLS 校验会失败。车辆上电让 GPS/NTP 同步后重试。" >&2
  exit 1
fi
echo "    时钟 OK: $(date)"

echo "==> [4/6] 从 $REPO_URL 克隆分支 $BRANCH"
sudo rm -rf "$TMP_PATH"
CLONE_ARGS=(--progress --depth=1 -b "$BRANCH")
if [ "$STRIPPED" != "1" ]; then
  CLONE_ARGS+=(--recurse-submodules --shallow-submodules)
fi
# LFS 对象先跳过（800MB 模型会把 clone 卡住），源码树安装稍后按需 lfs pull
if ! GIT_LFS_SKIP_SMUDGE=1 git clone "${CLONE_ARGS[@]}" "$REPO_URL" "$TMP_PATH" 2>&1 | tail -3; then
  echo "错误：克隆失败。检查设备网络与分支名（GitHub 国内直连不稳定时建议 SOURCE=cnb）。" >&2
  exit 1
fi

echo "==> [5/6] 校验并替换 $INSTALL_PATH"
if [ ! -f "$TMP_PATH/launch_openpilot.sh" ]; then
  echo "错误：分支内容校验失败（缺 launch_openpilot.sh），不是有效的可安装树" >&2
  exit 1
fi
if [ "$STRIPPED" = "1" ]; then
  SRC_COMMIT=$(head -c 12 "$TMP_PATH/git_src_commit")
else
  # 源码树：submodules 已随 clone 拉取；LFS 文件（updater zipapp 等）现在补拉
  if ! command -v git-lfs >/dev/null 2>&1; then
    echo "    设备无 git-lfs，尝试 apt 安装..."
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y git-lfs >/dev/null 2>&1 \
      || sudo sh -c 'DEBIAN_FRONTEND=noninteractive apt-get update -qq && apt-get install -y git-lfs' >/dev/null 2>&1 || true
  fi
  if command -v git-lfs >/dev/null 2>&1; then
    echo "    git lfs pull（跳过 800MB big 模型，与 CI 打包口径一致）..."
    (cd "$TMP_PATH" && git lfs install --local >/dev/null && \
     git lfs pull --exclude="*big_driving_tinygrad.pkl") || {
      echo "错误：LFS 拉取失败（updater zipapp 是 LFS 文件，缺了设备装完无法自更新）。请检查网络后重试。" >&2
      exit 1
    }
  else
    echo "错误：设备无 git-lfs 且自动安装失败，GitHub 源码树安装无法继续（staging 精简树不受影响）。" >&2
    exit 1
  fi
  SRC_COMMIT=$(git -C "$TMP_PATH" rev-parse --short=12 HEAD)
fi
mkdir -p /data/safe_staging
sudo rm -rf "$BACKUP"
if [ -d "$INSTALL_PATH" ]; then
  echo "    旧安装备份到 $BACKUP"
  mv "$INSTALL_PATH" "$BACKUP"
fi
mv "$TMP_PATH" "$INSTALL_PATH"
chmod +x "$INSTALL_PATH"/launch_*.sh 2>/dev/null || true
echo "    已安装: $SOURCE/$BRANCH @ $SRC_COMMIT"

echo "==> [6/6] 写入 continue.sh 并重启 openpilot"
cat > /data/continue.sh.new <<'EOF'
#!/usr/bin/env bash
cd /data/openpilot
exec ./launch_openpilot.sh
EOF
chmod +x /data/continue.sh.new
mv /data/continue.sh.new "$CONTINUE"
mkdir -p /data/params/d
echo -n "1" > /data/params/d/SshEnabled
sync

if sudo systemctl start comma.service 2>/dev/null; then
  echo "完成！openpilot 已重启（comma.service），屏幕将在 1-2 分钟内进入主界面。"
  if [ "$STRIPPED" != "1" ]; then
    echo "注意：源码树安装首次启动需在设备上 scons 编译（约 20-40 分钟），期间黑屏/慢属正常。"
  fi
else
  echo "完成！但 comma.service 启动失败，10 秒后重启设备..."
  sleep 10
  sudo reboot
fi
echo "回滚方法（如需恢复旧版本）："
echo "  ssh comma@<设备IP> 'mv $BACKUP $INSTALL_PATH && sudo reboot'"
