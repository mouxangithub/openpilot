#!/usr/bin/env bash
# CNB 一键安装/重装脚本 —— 绕过 AGNOS 安装器 UI，直接从 CNB 镜像仓库安装。
#
# 原理：等价于官方 installer.cc 的安装流程
#   git clone <CNB 仓库> -b <分支> --depth=1 /data/tmppilot
#   → 校验 → 替换 /data/openpilot → 写 /data/continue.sh → 重启 openpilot
# CNB 为国内 CDN（cnb.cool），无需科学上网，速度远快于 installer.comma.ai。
#
# 用法一（推荐，PC 上执行，设备开机后 SSH 可达即可）：
#   ssh comma@<设备IP> "bash -s" < tools/release/cnb-install.sh
#
# 用法二（设备已装过本脚本所属版本时自举/重装）：
#   ssh comma@<设备IP> "curl -fsSL https://cnb.cool/mouxancnb/openpilot/-/git/raw/staging/scripts/cnb-install.sh | bash"
#
# 可选环境变量（用法一在命令前传入，用法二用 bash -s 前的 export）：
#   CNB_BRANCH  要安装的分支（默认 staging，可改为 test-prebuild 等）
#   CNB_REPO_URL 仓库地址（默认 https://cnb.cool/mouxancnb/openpilot.git）
#
# 脚本本身跑在设备上（comma 用户）。

REPO_URL="${CNB_REPO_URL:-https://cnb.cool/mouxancnb/openpilot.git}"
BRANCH="${CNB_BRANCH:-staging}"

INSTALL_PATH=/data/openpilot
TMP_PATH=/data/tmppilot
CONTINUE=/data/continue.sh
BACKUP=/data/safe_staging/old_openpilot_cnb_install
MIN_TIME=1735689600   # 2025-01-01，时钟早于它视为无效（git/TLS 会失败）

set -u

echo "==> [1/6] 检查运行环境"
if [ "$(id -u)" = "0" ]; then
  echo "错误：请以 comma 用户运行（不要用 sudo bash）" >&2
  exit 1
fi
if [ ! -d /data ] || ! grep -q 'tici\|mici\|tizi' /sys/firmware/devicetree/base/model 2>/dev/null; then
  echo "警告：未检测到 comma 设备型号，继续执行（测试环境请忽略）" >&2
fi
AVAIL_KB=$(df -Pk /data | awk 'NR==2 {print $4}')
echo "    /data 可用空间: $((AVAIL_KB / 1024)) MB"
if [ "$AVAIL_KB" -lt 5242880 ]; then
  echo "错误：/data 可用空间不足 5GB，先清理旧安装（删除 /data/safe_staging/ 下旧目录）" >&2
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
  HTTP_DATE=$(curl -fsSI https://cnb.cool 2>/dev/null | grep -i '^date:' | cut -d' ' -f2- | tr -d '\r')
  if [ -n "$HTTP_DATE" ]; then
    echo "    从 CNB 服务器校时: $HTTP_DATE"
    sudo date -s "$HTTP_DATE" >/dev/null || true
  fi
fi
if [ "$(date +%s)" -lt "$MIN_TIME" ]; then
  echo "错误：系统时钟无效且校时失败，git 克隆 TLS 校验会失败。车辆上电让 GPS/NTP 同步后重试。" >&2
  exit 1
fi
echo "    时钟 OK: $(date)"

echo "==> [4/6] 从 CNB 克隆 $REPO_URL (分支 $BRANCH)"
sudo rm -rf "$TMP_PATH"
# 与 installer.cc 一致：depth=1 + 进度输出。staging 分支已内含全部文件（无 submodule、无 LFS 指针）。
if ! git clone --progress "$REPO_URL" -b "$BRANCH" --depth=1 "$TMP_PATH" 2>&1 | tail -3; then
  echo "错误：克隆失败。检查设备网络（蜂窝/WiFi）与分支名。" >&2
  exit 1
fi

echo "==> [5/6] 校验并替换 $INSTALL_PATH"
if [ ! -x "$TMP_PATH/launch_openpilot.sh" ] || [ ! -f "$TMP_PATH/git_src_commit" ]; then
  echo "错误：分支内容校验失败（缺 launch_openpilot.sh 或 git_src_commit），不是有效的精简发布树" >&2
  exit 1
fi
SRC_COMMIT=$(head -c 12 "$TMP_PATH/git_src_commit")
mkdir -p /data/safe_staging
sudo rm -rf "$BACKUP"
if [ -d "$INSTALL_PATH" ]; then
  echo "    旧安装备份到 $BACKUP"
  mv "$INSTALL_PATH" "$BACKUP"
fi
mv "$TMP_PATH" "$INSTALL_PATH"
chmod +x "$INSTALL_PATH"/launch_*.sh 2>/dev/null || true
echo "    已安装版本: $BRANCH @ $SRC_COMMIT"

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
else
  echo "完成！但 comma.service 启动失败，10 秒后重启设备..."
  sleep 10
  sudo reboot
fi
echo "回滚方法（如需恢复旧版本）："
echo "  ssh comma@<设备IP> 'mv $BACKUP $INSTALL_PATH && sudo reboot'"
