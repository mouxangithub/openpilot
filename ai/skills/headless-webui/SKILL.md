# 无屏模式与 WebUI 全功能

C3/C3X **无内置屏**、用户说「无屏」「headless」「WebUI 怎么用」「5080 设置」「AGNOS 怎么更」时启用。

> 事实来源：`ai/docs/HEADLESS_WEBUI.md`、`webui/server/routes/__init__.py`

## 何时触发

- 设备无触摸屏 / 仅 SSH / 侧载无屏板
- `OPENPILOT_HEADLESS=1` 或 `WebuiHeadlessMode=on|auto` 且探测无屏
- 用户要通过 **浏览器** 完成设置、Wi-Fi、OTA、AGNOS、模型切换
- native `ui` 不启动、manager 错误在 `/tmp/manager_last_error.txt`

## 第一步：环境确认

1. `get_host_environment` — 车机 vs PC、`hardware_profile.lite`
2. `webui_service_status` — :5080
3. `webui_headless_status` — `effective_headless`、`has_builtin_display`
4. `webui_health_check` — 返回可打开 URL（带 `?v=`）
5. 若 onboarding 未完成：`webui_onboarding_status`

## 无屏模式控制

| 方式 | 说明 |
|------|------|
| Param `WebuiHeadlessMode` | `auto` / `on` / `off`（无硬件时不能 `off`） |
| WebUI API | `PUT /api/opui/headless-mode` `{"mode":"on"}` |
| 环境变量 | `OPENPILOT_HEADLESS=1`（启动时，需重启 manager） |
| op助手 | `write_params({"WebuiHeadlessMode":"on"}, confirm=true)` 后 `manager_control` restart |

改 `WebuiHeadlessMode` 后建议重启 manager，使 `ui` 进程策略生效。

## WebUI 能做什么（无屏主界面）

告诉用户：**所有原 BIG UI 设置** 在 WebUI Settings 15 面板中：

`device` · `network` · `sunnylink` · `toggles` · `software` · `models` · `steering` · `cruise` · `visuals` · `display` · `osm` · `trips` · `vehicle` · `firehose` · `developer`

### 高频操作指引

| 用户需求 | WebUI 路径 | API（AI 可读） |
|----------|------------|----------------|
| 连 Wi-Fi | Settings → Network → Scan | `GET/POST /api/opui/wifi/*` |
| 系统/分支更新 | Settings → Software | `GET /api/opui/software` |
| **AGNOS 升级**（无屏必走） | Software → AGNOS | `GET /api/opui/agnos` → `POST install` |
| 换驾驶模型 | Settings → Models | `GET /api/opui/models` |
| 换车型平台 | Settings → Vehicle | `GET /api/opui/vehicle/platforms` |
| 语言 | Device → Language | `POST /api/opui/device/language`；与 GUI 同步 |
| 重启/关机 | Device 底部 | `POST /api/opui/action/reboot` 等 |
| manager 起不来 | Software 或 Developer | `GET /api/opui/system/manager_error` |
| 前路画面 | Onroad 页 | WebRTC `webrtc/offer` |
| 离线地图 | OSM 面板 | `GET/POST /api/opui/osm/*` |

### 实时状态

- WebSocket `ws://<IP>:5080/ws/opui`（state / home / panel / put_param）
- AI 诊断优先：`webui_health_check` + `curl /api/opui/state`

## op助手 与 WebUI 分工

| 任务 | 推荐 |
|------|------|
| 图形设置、Wi-Fi、AGNOS | **引导用户打开 WebUI** 或读 API |
| 批量调参、路线分析、SecOC | **op助手** `:5090` 工具 |
| 上车 overlay 验收 | 技能 `webui-vehicle-qa` + scrcpy（有屏对照） |

## 服务排障

```bash
pgrep -af 'webui\.webuid'
tail -30 /tmp/webui.log
curl -s http://127.0.0.1:5080/api/opui/bootstrap
curl -s http://127.0.0.1:5080/api/opui/headless-mode
```

车机启动需 `PYTHONPATH` 含 openpilot 根与 `.pydeps`（见 `launch_chffrplus.sh`）。

## 安全

- 行驶中：只读 API / `webui_health_check`；不写 Param、不 AGNOS install
- 无屏已清 `IsDriverViewEnabled` — 勿建议开 driver view 阻塞 onroad
- Lite：无 `soundd`，用 `set_sp_dev_beep`（技能 `c3-lite`）

## 相关技能

- `webui-development` — PC 预览与 Dev 预设
- `webui-vehicle-qa` — 上车验收
- `git-lfs-fork` — 推送代码（与 WebUI 无关）
- `sp-display-device` — 亮度 Param（有屏或 WebUI Display）
