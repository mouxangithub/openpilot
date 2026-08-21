# op Web UI（openpilot 设备界面 Web 镜像）

与 `ai/` **并行**的独立子仓库：在浏览器中复刻 sunnypilot BIG UI（15 个设置面板 + 行车 HUD + WebRTC 相机）。

| 项目 | 说明 |
|------|------|
| 安装位置 | `<openpilot>/webui`（git submodule） |
| Web 入口 | `http://<设备IP>:5080` |
| 进程入口 | `python3 -m webui.webuid` |
| 版本标识 | **当前 git commit**（`bootstrap.version`），非语义化版本号 |
| 与 ai | 独立进程、独立端口（ai `:5090`） |

## 功能（v0.4 / GUI v55）

### 设置面板（15 个，对齐 sunnypilot BIG UI）

Device · Network · sunnylink · Toggles · Software · Models · Steering · Cruise · Visuals · Display · OSM · Trips · Vehicle · Firehose · Developer

- Params 读写（bool / int / choice / readonly）
- 系统动作：重启、关机、卸载、标定重置、**openpilot 固件 updater**、sunnylink 备份
- Wi-Fi 扫描与连接（NetworkManager / WifiManager）
- Software 分支切换与更新状态（**整包 openpilot**，与 Web UI 自更新无关）

### 行车界面（Onroad）

- 状态机：HOME / SETTINGS / ONROAD
- 边框四色、HUD、侧栏指标、告警（含 full 布局）
- WebRTC 前路/驾驶员相机
- 模型叠加：车道线、路径色带、实验渐变、彩虹路径、Chevron 指标

### Web UI 自更新（git）

与首页 **UPDATE** 药丸、Software 面板的 **openpilot 更新** 完全分离，只更新 `webui/` 子仓库：

1. 后台定期 `git fetch`，比较 `HEAD` 与 `origin/<branch>`
2. 有新提交时弹出 **Web UI update** 对话框（可「稍后」或「立即更新」）
3. 「稍后」会记住远端 commit，直到出现更新的提交才再提示
4. **Device** 面板底部可随时「检查更新 / 立即更新」重新打开对话框
5. 「立即更新」执行 `git pull --ff-only origin <branch>`，完成后强刷页面

不会修改 openpilot 主仓库或触发 `updated` 服务。

## PC 本地预览

```bash
py -3 webui/dev/run_pc.py --port 5080
# 浏览器 http://127.0.0.1:5080/?v=55
```

右下角 **Dev 模拟面板** 可切换离路/行驶/告警。详见 [dev/README.md](dev/README.md)。

**是否 1:1 还原车机 UI？** 布局与交互已高度对齐；完整差距见 [docs/GUI_ALIGNMENT.md](docs/GUI_ALIGNMENT.md)。

## 快速开始（车机）

```bash
curl -fsSL https://raw.githubusercontent.com/mouxangithub/webui/main/install/install.sh | bash
```

或已有 openpilot 环境：

```bash
export OPENPILOT_ROOT=/data/openpilot
cd "$OPENPILOT_ROOT" && PYTHONPATH="$OPENPILOT_ROOT" python3 -m webui.webuid --port 5080
```

## 如何更新 Web UI

### 方式 A：界面内（推荐）

1. 确保 `webui` 为 git 检出且能访问 `origin`（车机需联网）
2. 打开 **设置 → 软件（Software）**，滚动到底部 **Web UI**
3. 有更新时弹窗或点 **UPDATE**；也可点 **CHECK** 手动检测

### 方式 B：命令行

在 openpilot 根目录：

```bash
cd webui
git fetch origin main
git pull --ff-only origin main
# 若改了 Python 服务端，重启 webui 进程；仅静态资源则浏览器强刷 ?v=55
```

### 与 openpilot 更新的区别

| | openpilot（Software / UPDATE 药丸） | Web UI（软件面板底部） |
|--|--|--|
| 范围 | 整包系统 / 分支 | 仅 `webui/` 子模块 |
| 机制 | `updated` + overlay | `git pull` |
| 重启 | 通常需 reboot | 通常只需刷新页面 |

## API 概览

| 端点 | 说明 |
|------|------|
| `GET /api/opui/bootstrap` | 启动元数据（含 git short commit） |
| `GET /api/opui/webui-update?fetch=1` | 检测 Web UI git 更新 |
| `POST /api/opui/webui-update/apply` | `git pull --ff-only` |
| `POST /api/opui/webui-update/dismiss` | 暂时忽略当前远端 commit |
| `GET /api/opui/panels` | 面板 schema |
| `GET /api/opui/state` | 行车/UI 状态 |
| `POST /api/opui/webrtc/offer` | WebRTC SDP |

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)（若存在）。

## 已知限制

- PC 上无 NetworkManager 时 Wi-Fi 面板显示不可用
- 模型叠加为 Canvas 近似，非原生 shader
- Web UI 自更新要求 `webui/.git` 存在且 `git fetch` 可达远端
