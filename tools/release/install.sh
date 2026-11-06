#!/usr/bin/env bash
# openpilot 一键安装/重装脚本（统一版）—— 绕过 AGNOS 安装器 UI，从任意 git 仓库安装。
#
# 支持的仓库主机（REPO_URL 填完整 clone 地址即可，脚本不关心主机是谁）：
#   github.com / gitlab.com / jihulab.com(极狐) / gitee.com / gitea.com /
#   gitcode.com / atomgit.com / codeup.aliyun.com(云效) / git.code.tencent.com(工蜂) /
#   codeberg.org / bitbucket.org / cnb.cool / 自建仓库（内网 IP / 域名均可）
# gh-proxy 加速仅对 GitHub 生效：REPO_URL 是 github.com 且直连失败时才自动走
#   gh-proxy.com 反代（含子仓库 insteadOf 重写）；其他主机一律直连，不走代理。
#
# 原理：等价于官方 installer.cc 的安装流程
#   git clone <REPO_URL> -b <BRANCH> --depth=1 /data/tmppilot
#   → 拉取子仓库（如有 .gitmodules）→ 拉取 LFS 资产（如有）→ 校验
#   → 替换 /data/openpilot → 写 /data/continue.sh → 重启 openpilot
#
# 源码树（带 .gitmodules/LFS，如 openpilot test 分支）与精简/第三方发布树
# （子仓库已并入，如 sunnypilot staging-tici）都支持：
#   - 源码树首次启动 scons 现场编译，进入主界面比发布树慢几分钟
#
# 用法（设备 SSH 可达即可，一条命令完成，不需要先传脚本）：
#   ssh comma@<设备IP> "curl -fsSL https://raw.githubusercontent.com/mouxangithub/openpilot/refs/heads/test/tools/release/install.sh | bash"
#
# GitHub raw 不可达时，脚本本体走 gh-proxy 反代拉取：
#   ssh comma@<设备IP> "curl -fsSL https://gh-proxy.com/https://raw.githubusercontent.com/mouxangithub/openpilot/refs/heads/test/tools/release/install.sh | bash"
#
# 或 PC 上先落地再管道推送：
#   ssh comma@<设备IP> "bash -s" < tools/release/install.sh
#
# 可选环境变量（放进 ssh 的引号内，注意加在 bash 前面）：
#   BRANCH=test         要安装的分支（默认 test）
#   REPO_URL=...        任意 git clone 地址（默认 https://github.com/mouxangithub/openpilot.git）
#                       例：https://gitee.com/用户/openpilot.git
#                           https://gitlab.com/用户/openpilot.git
#                           http://192.168.1.10:3000/用户/openpilot.git（自建 Gitea）
#   GITHUB_USER=...     SSH 公钥来源 GitHub 用户名（默认 mouxangithub，注入到 GithubSshKeys）
#   GH_PROXY=...        GitHub 反代地址（默认 https://gh-proxy.com，仅 REPO_URL 为 github.com
#                       且直连失败时启用；设为 direct 强制直连）
#                       注意：gh-proxy 不代理 LFS batch API，LFS 仍需 GitHub 直连
#
# 脚本跑在设备上（comma 用户）。

REPO_URL="${REPO_URL:-https://github.com/mouxangithub/openpilot.git}"
BRANCH="${BRANCH:-test}"

INSTALL_PATH=/data/openpilot
TMP_PATH=/data/tmppilot
CONTINUE=/data/continue.sh
BACKUP=/data/safe_test/old_openpilot_github_install
MIN_TIME=1735689600   # 2025-01-01，时钟早于它视为无效（git/TLS 会失败）

set -u -o pipefail

echo "==> [1/6] 检查运行环境（分支=$BRANCH）"
if [ "$(id -u)" = "0" ]; then
  echo "错误：请以 comma 用户运行（不要用 sudo bash）" >&2
  exit 1
fi
# 空间门槛：默认 test 源码树（子仓库+LFS+scons 编译）需 7GB；其他仓库按 5GB 起步，
# 若同样是源码树仍可能超 5GB，装完失败时按提示清理重试。
AVAIL_KB=$(df -Pk /data | awk 'NR==2 {print $4}')
echo "    /data 可用空间: $((AVAIL_KB / 1024)) MB"
if [ "$REPO_URL" = "https://github.com/mouxangithub/openpilot.git" ] && [ "$BRANCH" = "test" ]; then
  MIN_KB=7340032
else
  MIN_KB=5242880
fi
if [ "$AVAIL_KB" -lt "$MIN_KB" ]; then
  echo "错误：/data 可用空间不足 $((MIN_KB / 1048576))GB。" >&2
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

echo "==> [4/6] 克隆 $REPO_URL (分支 $BRANCH)"
sudo rm -rf "$TMP_PATH"
# gh-proxy 仅加速 GitHub：REPO_URL 是 github.com 且直连失败才重试代理（git smart
# 协议已实测可用）；其他主机（gitee/自建等）一律直连。GH_PROXY=direct 强制直连。
GH_PROXY="${GH_PROXY:-https://gh-proxy.com}"
case "$REPO_URL" in
  *github.com*) IS_GITHUB=1 ;;
  *)            IS_GITHUB="" ;;
esac
git_clone() {  # $1=克隆用的 URL 重写参数（空=直连）
  if [ -n "$1" ]; then
    git -c "url.$1/https://github.com/.insteadOf=https://github.com/" \
      clone --progress "$REPO_URL" -b "$BRANCH" --depth=1 "$TMP_PATH" 2>&1 | tail -3
  else
    git clone --progress "$REPO_URL" -b "$BRANCH" --depth=1 "$TMP_PATH" 2>&1 | tail -3
  fi
}
PROXY_MODE=""
if [ "$GH_PROXY" = "direct" ] || [ -z "$IS_GITHUB" ]; then
  git_clone "" || { echo "错误：直连克隆失败。检查设备网络、仓库地址与分支名。" >&2; exit 1; }
elif git_clone ""; then
  :
else
  echo "    GitHub 直连失败，自动改走代理 $GH_PROXY 重试..."
  sudo rm -rf "$TMP_PATH"
  if git_clone "$GH_PROXY"; then
    PROXY_MODE=1
    # 把 insteadOf 写进 repo config：子仓库 URL 若是 github.com 开头，submodule update 一并走代理
    git -C "$TMP_PATH" config "url.$GH_PROXY/https://github.com/.insteadOf" "https://github.com/"
  else
    echo "错误：直连与代理克隆均失败。检查设备网络（蜂窝/WiFi）与分支名。" >&2
    exit 1
  fi
fi

# ---- 子仓库：源码树带 .gitmodules 才需要拉（发布树/第三方并入树没有）----
# launch_chffrplus.sh 的 link_repos() 只建 symlink，不会拉仓库；缺了它们 scons/import 全挂。
if [ -f "$TMP_PATH/.gitmodules" ]; then
  SOURCE_TREE=1
  echo "    检测到 .gitmodules，拉取子仓库（浅克隆，可能需要几分钟）..."
  if ! git -C "$TMP_PATH" submodule update --init --progress --depth=1 --recursive 2>&1 | tail -5; then
    echo "错误：子仓库拉取失败。检查设备网络后重试。" >&2
    exit 1
  fi
  N_SUB=$(git -C "$TMP_PATH" submodule status --recursive 2>/dev/null | grep -cv '^-' || true)
  echo "    子仓库就绪: $N_SUB 个已 checkout"
else
  echo "    无 .gitmodules（子仓库已并入或为发布树），跳过子仓库拉取"
fi

# ---- LFS 资产：源码树带 LFS 指针（字体/动画/模型等），无指针则跳过 ----
# 设备端 .gitconfig 已带 lfs filter，clone checkout 时通常已自动 smudge；
# 这里显式兜底拉取 + 指针校验，防止 LFS CDN 抖动留下指针占位。
# 注意：gh-proxy 不代理 LFS batch API（/info/lfs），代理模式下 LFS 仍走直连 GitHub。
git -C "$TMP_PATH" lfs install --local >/dev/null 2>&1 || true
if git -C "$TMP_PATH" lfs ls-files 2>/dev/null | grep -q .; then
  echo "    检测到 LFS 指针，拉取 LFS 资产..."
  if ! git -C "$TMP_PATH" lfs pull >/dev/null 2>&1; then
    echo "错误：主仓 LFS 拉取失败（字体/动画/模型文件仍是指针占位）。检查网络后重试。" >&2
    [ -n "$PROXY_MODE" ] && echo "      提示：gh-proxy 不支持 LFS，LFS 需直连 GitHub；可临时开手机热点重跑本脚本。" >&2
    exit 1
  fi
  # 子仓库自身的 LFS（如 ai 仓库内模型）逐仓兜底；个别子仓无 LFS 时 git lfs pull 静默成功。
  git -C "$TMP_PATH" submodule foreach --recursive git lfs pull >/dev/null 2>&1 || \
    echo "    警告：个别子仓库 LFS 拉取未完成（不影响主程序，ai 模型缺失时相关功能不可用）"
else
  echo "    无 LFS 指针文件，跳过 LFS 拉取"
fi

echo "==> [5/6] 校验并替换 $INSTALL_PATH"
# 统一用 git rev-parse 取版本（打包树的 git_src_commit 与 HEAD 一致，源码树没有该文件）
if [ ! -x "$TMP_PATH/launch_openpilot.sh" ]; then
  echo "错误：分支内容校验失败（缺 launch_openpilot.sh），不是有效的 openpilot 树" >&2
  exit 1
fi
# LFS 指针残留校验：真字体二进制不可能以 "version https://git-lfs" 开头；
# 第三方树无此字体文件时跳过（指针残留已在 [4/6] LFS 拉取环节拦截）。
LFS_PROBE="$TMP_PATH/openpilot/selfdrive/assets/fonts/Inter-Regular.ttf"
if [ -f "$LFS_PROBE" ] && head -c 30 "$LFS_PROBE" | grep -q "git-lfs"; then
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
if [ -n "${SOURCE_TREE:-}" ]; then
  echo "    提示：源码树首次启动会 scons 现场编译，进入主界面约需 3-5 分钟，属正常现象"
fi

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
# 公钥默认取仓库内 tools/release/github_keys.txt（mouxangithub 的 6 把 ed25519），
# 四条通道逐级降级：CNB raw（国内直连）→ GitHub raw → gh-proxy raw → github.com/<user>.keys。
GITHUB_USER="${GITHUB_USER:-mouxangithub}"
KEYS_TMP=/data/params/d/GithubSshKeys.new
rm -f "$KEYS_TMP"
KEYS_PATH_RAW="mouxangithub/openpilot/refs/heads/test/tools/release/github_keys.txt"
fetch_keys() {
  # 默认用户：优先仓库内公钥文件（CNB/GitHub/代理三通道；公钥文件固定取 test 分支）
  if [ "$GITHUB_USER" = "mouxangithub" ]; then
    curl -fsSL -m 20 "https://cnb.cool/mouxancnb/openpilot/-/git/raw/test/tools/release/github_keys.txt" -o "$KEYS_TMP" 2>/dev/null && [ -s "$KEYS_TMP" ] && return 0
    curl -fsSL -m 20 "https://raw.githubusercontent.com/$KEYS_PATH_RAW" -o "$KEYS_TMP" 2>/dev/null && [ -s "$KEYS_TMP" ] && return 0
    [ "$GH_PROXY" != "direct" ] && curl -fsSL -m 20 "$GH_PROXY/https://raw.githubusercontent.com/$KEYS_PATH_RAW" -o "$KEYS_TMP" 2>/dev/null && [ -s "$KEYS_TMP" ] && return 0
  fi
  # 自定义用户或仓库文件全部失败：GitHub .keys 端点（直连/代理）
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
  if [ -n "${SOURCE_TREE:-}" ]; then
    echo "完成！openpilot 已重启（comma.service），首次启动 scons 编译后 3-5 分钟进入主界面。"
  else
    echo "完成！openpilot 已重启（comma.service），屏幕将在 1-2 分钟内进入主界面。"
  fi
else
  echo "完成！但 comma.service 启动失败，10 秒后重启设备..."
  sleep 10
  sudo reboot
fi
echo "回滚方法（如需恢复旧版本）："
echo "  ssh comma@<设备IP> 'mv $BACKUP $INSTALL_PATH && sudo reboot'"
