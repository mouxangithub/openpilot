#!/usr/bin/env bash
# GITHUB 一键安装/重装脚本 —— 绕过 AGNOS 安装器 UI，直接从 GITHUB 仓库安装 test 源码分支。
#
# 原理：等价于官方 installer.cc 的安装流程
#   git clone https://github.com/mouxangithub/openpilot.git -b test --depth=1 --recurse-submodules /data/tmppilot
#   → 拉取子仓库 → 拉取 LFS 资产 → 校验 → 替换 /data/openpilot → 写 /data/continue.sh → 重启 openpilot
#
# 注意：test 是完整源码树，与 staging 精简发布树的区别：
#   - 带 10 个 git 子仓库（panda/opendbc/msgq/tinygrad/rednose/teleoprtc/jetlink/ai/webui/neural_network_data）
#   - 带 268 个 LFS 资产（字体/动画/模型/二进制），设备端 carrot AGNOS 自带 git-lfs
#   - 首次启动 scons 现场编译，进入主界面比 staging 慢几分钟
#
# 用法（设备 SSH 可达即可，一条命令完成，不需要先传脚本）：
#   ssh comma@<设备IP> "curl -fsSL https://raw.githubusercontent.com/mouxangithub/openpilot/refs/heads/test/tools/release/install.sh | bash"
#
# 或 PC 上先落地再管道推送（raw.githubusercontent.com 不可达时的替代）：
#   ssh comma@<设备IP> "bash -s" < tools/release/install.sh
#
# 可选环境变量（放进 ssh 的引号内）：
#   BRANCH=test         要安装的 GitHub 分支（默认 test）
#   REPO_URL=...        GitHub 仓库地址（默认 https://github.com/mouxangithub/openpilot.git）
#   GITHUB_USER=...     SSH 公钥来源 GitHub 用户名（默认 mouxangithub，注入到 GithubSshKeys）
#
# 脚本跑在设备上（comma 用户）。

REPO_URL="${REPO_URL:-https://github.com/mouxangithub/openpilot.git}"
BRANCH="${BRANCH:-test}"

INSTALL_PATH=/data/openpilot
TMP_PATH=/data/tmppilot
CONTINUE=/data/continue.sh
BACKUP=/data/safe_test/old_openpilot_github_install
MIN_TIME=1735689600   # 2025-01-01，时钟早于它视为无效（git/TLS 会失败）

set -u

echo "==> [1/6] 检查运行环境（分支=$BRANCH）"
if [ "$(id -u)" = "0" ]; then
  echo "错误：请以 comma 用户运行（不要用 sudo bash）" >&2
  exit 1
fi
# test 源码树 = 主仓 + 10 个子仓库 + LFS 对象 + scons 编译产物，比 staging 精简树大得多
AVAIL_KB=$(df -Pk /data | awk 'NR==2 {print $4}')
echo "    /data 可用空间: $((AVAIL_KB / 1024)) MB"
if [ "$AVAIL_KB" -lt 7340032 ]; then
  echo "错误：/data 可用空间不足 7GB（test 源码树含子仓库与 LFS，比精简树大）。" >&2
  echo "      先清理旧安装：ls /data/safe_test/ /data/safe_staging/ 再删旧目录" >&2
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
  for TSYNC_URL in http://github.com http://www.qq.com http://www.baidu.com; do
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

echo "==> [4/6] 从 GITHUB 克隆 $REPO_URL (分支 $BRANCH)"
sudo rm -rf "$TMP_PATH"
# 与 installer.cc 一致：depth=1 + 进度输出。分步克隆比 --recurse-submodules 可控，逐仓报错。
if ! git clone --progress "$REPO_URL" -b "$BRANCH" --depth=1 "$TMP_PATH" 2>&1 | tail -3; then
  echo "错误：克隆失败。检查设备网络（蜂窝/WiFi）与分支名。" >&2
  exit 1
fi

# ---- 子仓库：test 分支带 .gitmodules（staging 精简树没有），必须拉齐 ----
# launch_chffrplus.sh 的 link_repos() 只建 symlink，不会拉仓库；缺了它们 scons/import 全挂。
echo "    拉取子仓库（10 个，浅克隆，可能需要几分钟）..."
if ! git -C "$TMP_PATH" submodule update --init --progress --depth=1 --recursive 2>&1 | tail -5; then
  echo "错误：子仓库拉取失败。检查设备网络后重试。" >&2
  exit 1
fi
N_SUB=$(git -C "$TMP_PATH" submodule status --recursive 2>/dev/null | grep -cv '^-' || true)
echo "    子仓库就绪: $N_SUB 个已 checkout"

# ---- LFS 资产：268 个文件（字体/动画/模型/comma updater 二进制）----
# 设备端 .gitconfig 已带 lfs filter，clone checkout 时通常已自动 smudge；
# 这里显式兜底拉取 + 指针校验，防止 GitHub LFS CDN 抖动留下指针占位。
echo "    拉取 LFS 资产（268 个文件）..."
git -C "$TMP_PATH" lfs install --local >/dev/null 2>&1 || true
if ! git -C "$TMP_PATH" lfs pull >/dev/null 2>&1; then
  echo "错误：主仓 LFS 拉取失败（字体/动画/模型文件仍是指针占位）。检查网络后重试。" >&2
  exit 1
fi
# 子仓库自身的 LFS（如 ai 仓库内模型）逐仓兜底；个别子仓无 LFS 时 git lfs pull 静默成功。
git -C "$TMP_PATH" submodule foreach --recursive git lfs pull >/dev/null 2>&1 || \
  echo "    警告：个别子仓库 LFS 拉取未完成（不影响主程序，ai 模型缺失时相关功能不可用）"

echo "==> [5/6] 校验并替换 $INSTALL_PATH"
# test 源码树没有 release 打包生成的 git_src_commit，用 git rev-parse 代替
if [ ! -x "$TMP_PATH/launch_openpilot.sh" ]; then
  echo "错误：分支内容校验失败（缺 launch_openpilot.sh），不是有效的 openpilot 树" >&2
  exit 1
fi
if [ ! -f "$TMP_PATH/.gitmodules" ]; then
  echo "错误：分支缺少 .gitmodules，子仓库不完整，scons 编译会失败" >&2
  exit 1
fi
# LFS 指针残留校验：真字体二进制不可能以 "version https://git-lfs" 开头
LFS_PROBE="$TMP_PATH/openpilot/selfdrive/assets/fonts/Inter-Regular.ttf"
if [ ! -s "$LFS_PROBE" ] || head -c 30 "$LFS_PROBE" | grep -q "git-lfs"; then
  echo "错误：LFS 资产仍是指针占位（$LFS_PROBE），字体/UI 资源将损坏" >&2
  exit 1
fi
SRC_COMMIT=$(git -C "$TMP_PATH" rev-parse --short=12 HEAD)
mkdir -p /data/safe_test
sudo rm -rf "$BACKUP"
if [ -d "$INSTALL_PATH" ]; then
  echo "    旧安装备份到 $BACKUP"
  mv "$INSTALL_PATH" "$BACKUP"
fi
mv "$TMP_PATH" "$INSTALL_PATH"
chmod +x "$INSTALL_PATH"/launch_*.sh 2>/dev/null || true
echo "    已安装版本: $BRANCH @ $SRC_COMMIT"
echo "    提示：test 源码树首次启动会 scons 现场编译，进入主界面约需 3-5 分钟，属正常现象"

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
GITHUB_USER="${GITHUB_USER:-mouxangithub}"
if curl -fsSL -m 20 "https://github.com/${GITHUB_USER}.keys" -o /data/params/d/GithubSshKeys.new \
   && [ -s /data/params/d/GithubSshKeys.new ] \
   && grep -qE '^(ssh-|ecdsa-|sk-)' /data/params/d/GithubSshKeys.new; then
  mv /data/params/d/GithubSshKeys.new /data/params/d/GithubSshKeys
  echo "    已注入 ${GITHUB_USER} 的 GitHub SSH 公钥（$(grep -cE '^(ssh-|ecdsa-|sk-)' /data/params/d/GithubSshKeys) 把）"
else
  rm -f /data/params/d/GithubSshKeys.new
  echo "    警告：拉取 ${GITHUB_USER} 的 GitHub 公钥失败，SSH 可能无法登录；可稍后手动写入 /data/params/d/GithubSshKeys" >&2
fi
echo -n "1" > /data/params/d/SshEnabled
sync

if sudo systemctl start comma.service 2>/dev/null; then
  echo "完成！openpilot 已重启（comma.service），首次启动 scons 编译后 3-5 分钟进入主界面。"
else
  echo "完成！但 comma.service 启动失败，10 秒后重启设备..."
  sleep 10
  sudo reboot
fi
echo "回滚方法（如需恢复旧版本）："
echo "  ssh comma@<设备IP> 'mv $BACKUP $INSTALL_PATH && sudo reboot'"
