#!/usr/bin/env bash
# CNB 一键安装/重装脚本 —— 绕过 AGNOS 安装器 UI，直接从 CNB 镜像仓库安装。
#
# 原理：等价于官方 installer.cc 的安装流程
#   git clone https://cnb.cool/mouxancnb/openpilot.git -b staging --depth=1 /data/tmppilot
#   → 校验 → 替换 /data/openpilot → 写 /data/continue.sh → 重启 openpilot
# 安装源固定为 CNB（国内 CDN 直连，无需科学上网）；本脚本本体从 GitHub raw
# 的 test 分支获取（永远最新版）。
#
# 用法（设备 SSH 可达即可，一条命令完成，不需要先传脚本）：
#   ssh comma@<设备IP> "curl -fsSL https://raw.githubusercontent.com/mouxangithub/openpilot/refs/heads/test/tools/release/cnb-install.sh | bash"
#
# 或 PC 上先落地再管道推送（raw.githubusercontent.com 不可达时的替代）：
#   ssh comma@<设备IP> "bash -s" < tools/release/cnb-install.sh
#
# 可选环境变量（放进 ssh 的引号内，注意加在 bash 前面）：
#   BRANCH=staging      要安装的分支（默认 staging）
#   REPO_URL=...        仓库地址（默认 https://cnb.cool/mouxancnb/openpilot.git，任意 git URL 均可）
#   GITHUB_USER=...     SSH 公钥来源 GitHub 用户名（默认 mouxangithub，注入到 GithubSshKeys）
#   GH_PROXY=...        公钥拉取的 GitHub 反代（默认 https://gh-proxy.com，CNB 通道正常时用不到）
#
# 第三方仓库示例（装 sunnypilot 的 staging-tici，子仓库已并入树内、无 LFS 硬依赖）：
#   ssh comma@<设备IP> "curl -fsSL https://cnb.cool/mouxancnb/openpilot/-/git/raw/test/tools/release/cnb-install.sh | REPO_URL=https://github.com/sunnypilot/sunnypilot.git BRANCH=staging-tici bash"
# 注意：带 .gitmodules/LFS 的源码树（如 openpilot test 分支）请改用 install.sh。
#
# 脚本跑在设备上（comma 用户）。

REPO_URL="${REPO_URL:-https://cnb.cool/mouxancnb/openpilot.git}"
BRANCH="${BRANCH:-staging}"

INSTALL_PATH=/data/openpilot
TMP_PATH=/data/tmppilot
CONTINUE=/data/continue.sh
BACKUP=/data/safe_staging/old_openpilot_cnb_install
MIN_TIME=1735689600   # 2025-01-01，时钟早于它视为无效（git/TLS 会失败）

set -u

echo "==> [1/6] 检查运行环境（分支=$BRANCH）"
if [ "$(id -u)" = "0" ]; then
  echo "错误：请以 comma 用户运行（不要用 sudo bash）" >&2
  exit 1
fi
AVAIL_KB=$(df -Pk /data | awk 'NR==2 {print $4}')
echo "    /data 可用空间: $((AVAIL_KB / 1024)) MB"
if [ "$AVAIL_KB" -lt 5242880 ]; then
  echo "错误：/data 可用空间不足 5GB，先清理旧安装（/data/safe_staging/ 下旧目录）" >&2
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
  # 校时必须走 HTTP(80)：HTTPS 的证书校验本身依赖有效时钟（鸡生蛋）。
  for TSYNC_URL in http://cnb.cool http://www.qq.com http://www.baidu.com; do
    HTTP_DATE=$(curl -fsSI -m 10 "$TSYNC_URL" 2>/dev/null | grep -i '^date:' | cut -d' ' -f2- | tr -d '\r')
    if [ -n "$HTTP_DATE" ]; then
      echo "    从 $TSYNC_URL 校时: $HTTP_DATE"
      sudo date -s "$HTTP_DATE" >/dev/null || true
      [ "$(date +%s)" -ge "$MIN_TIME" ] && break
    fi
  done
fi
if [ "$(date +%s)" -lt "$MIN_TIME" ]; then
  echo "错误：系统时钟无效且校时失败，git 克隆 TLS 校验会失败。车辆上电让 GPS/NTP 同步后重试。" >&2
  exit 1
fi
echo "    时钟 OK: $(date)"

echo "==> [4/6] 克隆 $REPO_URL (分支 $BRANCH)"
sudo rm -rf "$TMP_PATH"
# 与 installer.cc 一致：depth=1 + 进度输出。staging 分支已内含全部文件（无 submodule、无 LFS 指针）。
if ! git clone --progress "$REPO_URL" -b "$BRANCH" --depth=1 "$TMP_PATH" 2>&1 | tail -3; then
  echo "错误：克隆失败。检查设备网络（蜂窝/WiFi）与分支名。" >&2
  exit 1
fi

echo "==> [5/6] 校验并替换 $INSTALL_PATH"
# 只硬性要求 launch_openpilot.sh：打包树（staging）带 git_src_commit，
# 第三方树（如 sunnypilot 的 staging-tici）没有，退回 git rev-parse。
if [ ! -x "$TMP_PATH/launch_openpilot.sh" ]; then
  echo "错误：分支内容校验失败（缺 launch_openpilot.sh），不是有效的 openpilot 树" >&2
  exit 1
fi
if [ -f "$TMP_PATH/git_src_commit" ]; then
  SRC_COMMIT=$(head -c 12 "$TMP_PATH/git_src_commit")
else
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
# AGNOS sshd 的 AuthorizedKeysFile 是 /data/params/d/GithubSshKeys /tmp/authorized_keys，
# 只认密钥（PasswordAuthentication no）。先注入公钥再写 SshEnabled，
# ssh-param-watcher 检测到 SshEnabled 变化后 set_ssh.sh 会拉起 sshd。
# 公钥默认取仓库内 tools/release/github_keys.txt，CNB raw 优先（国内直连最快），
# GitHub raw / gh-proxy raw 降级；自定义用户走 github.com/<user>.keys。
GITHUB_USER="${GITHUB_USER:-mouxangithub}"
KEYS_TMP=/data/params/d/GithubSshKeys.new
rm -f "$KEYS_TMP"
GH_PROXY="${GH_PROXY:-https://gh-proxy.com}"
fetch_keys() {
  if [ "$GITHUB_USER" = "mouxangithub" ]; then
    curl -fsSL -m 20 "https://cnb.cool/mouxancnb/openpilot/-/git/raw/$BRANCH/tools/release/github_keys.txt" -o "$KEYS_TMP" 2>/dev/null && [ -s "$KEYS_TMP" ] && return 0
    curl -fsSL -m 20 "https://raw.githubusercontent.com/mouxangithub/openpilot/refs/heads/test/tools/release/github_keys.txt" -o "$KEYS_TMP" 2>/dev/null && [ -s "$KEYS_TMP" ] && return 0
    [ "$GH_PROXY" != "direct" ] && curl -fsSL -m 20 "$GH_PROXY/https://raw.githubusercontent.com/mouxangithub/openpilot/refs/heads/test/tools/release/github_keys.txt" -o "$KEYS_TMP" 2>/dev/null && [ -s "$KEYS_TMP" ] && return 0
  fi
  curl -fsSL -m 20 "https://github.com/${GITHUB_USER}.keys" -o "$KEYS_TMP" 2>/dev/null && [ -s "$KEYS_TMP" ] && return 0
  [ "$GH_PROXY" != "direct" ] && curl -fsSL -m 20 "$GH_PROXY/https://github.com/${GITHUB_USER}.keys" -o "$KEYS_TMP" 2>/dev/null && [ -s "$KEYS_TMP" ] && return 0
  return 1
}
if fetch_keys && grep -qE '^(ssh-|ecdsa-|sk-)' "$KEYS_TMP"; then
  mv "$KEYS_TMP" /data/params/d/GithubSshKeys
  echo "    已注入 SSH 公钥（$(grep -cE '^(ssh-|ecdsa-|sk-)' /data/params/d/GithubSshKeys) 把，来源 $GITHUB_USER）"
else
  rm -f "$KEYS_TMP"
  echo "    警告：所有通道拉取公钥失败，SSH 可能无法登录；可稍后手动写入 /data/params/d/GithubSshKeys" >&2
fi
echo -n "1" > /data/params/d/SshEnabled
# 保险带：AuthorizedKeysFile 的第二通道 + 预生成主机密钥（避免首启 ExecStartPre 依赖）
cp /data/params/d/GithubSshKeys /tmp/authorized_keys 2>/dev/null || true
sudo ssh-keygen -A -f /data >/dev/null 2>&1 || true
sync
# ---- SSH 自检：参数注入成功 ≠ sshd 已拉起。sshd 由 ssh-param-watcher 拉起，
# .path 只监听 SshEnabled 的"修改事件"，rootfs 若没启用 watcher.service 开机自启，
# 重启后 sshd 无人拉起（launch_chffrplus.sh 已加开机兜底，双保险）。
sleep 2
if sudo systemctl is-active --quiet ssh; then
  echo "    sshd 运行中，监听 22 端口。设备 IP: $(hostname -I 2>/dev/null || ip -4 addr show 2>/dev/null | grep -oE 'inet 192[0-9.]*' | awk '{print $2}' | tr '\n' ' ')"
else
  echo "    警告：sshd 未运行，尝试手动拉起..." >&2
  sudo systemctl start ssh && echo "    sshd 已拉起，设备 IP: $(hostname -I 2>/dev/null)" || echo "    错误：sshd 拉起失败，请串口执行 'sudo systemctl start ssh' 排查" >&2
fi

if sudo systemctl start comma.service 2>/dev/null; then
  echo "完成！openpilot 已重启（comma.service），屏幕将在 1-2 分钟内进入主界面。"
else
  echo "完成！但 comma.service 启动失败，10 秒后重启设备..."
  sleep 10
  sudo reboot
fi
echo "回滚方法（如需恢复旧版本）："
echo "  ssh comma@<设备IP> 'mv $BACKUP $INSTALL_PATH && sudo reboot'"
