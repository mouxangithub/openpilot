# 无屏模式与 WebUI 操作指南（op助手）

无屏 C3/C3X 不跑原生 `ui` 进程，**WebUI（:5080）** 是唯一图形界面；**op助手（:5090）** 提供 AI 聊天与车机工具。

> WebUI 验收见 `ai/docs/WEBUI_QA.md`；交接见 `webui/docs/OP_ASSISTANT_HANDOFF.md`。

---

## 1. 无屏模式如何判定

### 硬件 / 启动探测（`launch_chffrplus.sh`）

- 环境变量 `OPENPILOT_HEADLESS=1|true|yes` → 强制无屏
- 或：存在背光节点但**无**触摸屏中断（`fts_ts` / i2c event）→ 自动无屏

### 运行时（`HARDWARE.has_builtin_display()`）

优先级（高 → 低）：

1. `OPENPILOT_HEADLESS=1` → 无屏；`=0` → 强制有屏（无硬件时 native ui 可能失败）
2. Param **`WebuiHeadlessMode`**：`auto` | `on` | `off`（持久化，与 GUI/WebUI 同步）
3. `probe_builtin_display()` 硬件探测

### WebUI API

```http
GET  /api/opui/headless-mode
PUT  /api/opui/headless-mode  {"mode":"auto"|"on"|"off"}
```

返回字段：`mode`、`effective_headless`、`has_builtin_display`、`can_turn_off`。

无屏时 `can_turn_off=false`（不能设为 `off`）。

### 无屏 vs Lite

| | 无屏（headless） | Lite C3 |
|--|------------------|---------|
| 含义 | 无内置屏/触控 | 无功放/无麦 |
| 原生 `ui` | **关** | 有屏时开 |
| `soundd` | 有屏时开 | **关** |
| `beepd` | — | **开**（`SpDevBeep`） |
| 主界面 | **WebUI** | 屏或 WebUI |

技能：`headless-webui`、`sp-device-lite`、`c3-lite`。

---

## 2. 无屏下的系统行为

- `process_config`：`ui` 仅在 `has_builtin_display()` 时启动
- manager 启动时：无屏会清除 `IsDriverViewEnabled`（否则阻塞 onroad）
- manager 崩溃：错误写入 `/tmp/manager_last_error.txt`（不弹原生 TextWindow）
- AGNOS 待更新：无屏**不**自动跑图形 updater → 用 **WebUI → Software → AGNOS** 或 SSH `agnos.py --swap`

### 服务端口

| 服务 | 端口 | 启动 |
|------|------|------|
| WebUI | **5080** | `launch_chffrplus.sh` → `start_webui`；`WEBUI_TLS=1` |
| op助手 | **5090** | `start_op_assistant`；`python3.12 -m ai.aid` |
| webrtcd | 5001 | 前路相机 WebRTC |

日志：`/tmp/webui.log`、`/tmp/aid.log`

### 访问

- 车机：`https://<车机IP>:5080/?v=<VERSION>`（或 HTTP，视 TLS 配置）
- PC 预览：`py -3 webui/dev/run_pc.py --port 5080`
- op助手：`http://<IP>:5090`

浏览器改参/设置后建议 **Ctrl+Shift+R** 强刷 `?v=` 与 `webui/VERSION` 一致。

---

## 3. WebUI 页面与功能

### 主界面

| 屏幕 | 功能 |
|------|------|
| **Home** | Prime/版本、更新提示、告警入口 |
| **Onroad** | WebRTC 前路相机 + Canvas overlay（车道/路径/前车）+ HUD |
| **Settings** | 15 个设置面板（见下） |
| **Onboarding** | 条款、训练、Sunnylink 引导 |

### 设置面板（`GET /api/opui/panels`）

| ID | 名称 | 要点 |
|----|------|------|
| `device` | 设备 | 配对、校准、语言、启动行为、离座关机、重启/关机 |
| `network` | 网络 | Wi-Fi 扫描/连接/忘记、信号、高级网络 |
| `sunnylink` | sunnylink | 云备份配对状态 |
| `toggles` | 开关 | OP 总开关、实验模式、纵向性格、Disengage on Accel |
| `software` | 软件 | 分支、更新、**AGNOS**、Git 信息 |
| `models` | 模型 | NN bundle 列表与切换 |
| `steering` | 转向 | MADS、变道、扭矩子面板 |
| `cruise` | 巡航 | SCC、限速 SLA 子面板 |
| `visuals` | 视觉 | 彩虹路径、DevUI、HUD 项 |
| `display` | 显示 | 亮度、熄屏、屏保 |
| `osm` | 离线地图 | 区域选择与下载 |
| `trips` | 行程 | 路线上传/管理 |
| `vehicle` | 车型 | CarPlatformBundle 选择 |
| `firehose` | Firehose | 数据上传相关 |
| `developer` | 开发者 | 高级开关、Runner、错误日志 |

子面板示例：`steering__mads`、`network__advanced`、`cruise__sla`。

### 实时同步

- **WebSocket** `ws://<host>:5080/ws/opui`
  - 推送：`state`（~200ms）、`home`（5s）、`panel`（参数变化）、`i18n`（语言）
  - 写入：`put_param`（断线回退 HTTP PUT）
- **HTTP 轮询**（仍用于 overlay ~100ms 等大数据）

`LanguageSetting` 与原生 GUI **双向同步**（`GET /api/opui/i18n`）。

---

## 4. WebUI HTTP API 索引（op助手 常用）

### 状态与健康

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/opui/bootstrap` | 首屏：版本、dev_pc、能力 |
| GET | `/api/opui/state` | 行车状态、侧栏指标 |
| GET | `/api/opui/home` | 首页卡片 |
| GET | `/api/opui/model/overlay` | overlay 几何（车道/路径） |
| GET | `/api/opui/system/manager_error` | manager 启动失败文本 |
| GET | `/api/opui/headless-mode` | 无屏模式状态 |

### 设置与参数

| 方法 | 路径 |
|------|------|
| GET | `/api/opui/panels` / `/api/opui/panels/{id}` |
| GET/PUT/DELETE | `/api/opui/params/{key}` |
| POST | `/api/opui/params/batch` |
| POST | `/api/opui/action/{action}` | 重启、关机等 |

### 网络 / Wi-Fi

| 方法 | 路径 |
|------|------|
| GET | `/api/opui/wifi/status` |
| GET | `/api/opui/wifi/scan` |
| POST | `/api/opui/wifi/connect` / `forget` / `connect/hidden` |
| GET | `/api/opui/network/advanced` |
| POST | `/api/opui/wifi/tethering` / `metered` |

### 软件 / AGNOS / WebUI 自更新

| 方法 | 路径 |
|------|------|
| GET | `/api/opui/software` |
| GET | `/api/opui/agnos` |
| POST | `/api/opui/agnos/install` / `agnos/reboot` |
| GET | `/api/opui/webui-update` |
| POST | `/api/opui/webui-update/apply` |

### 相机 / WebRTC

| 方法 | 路径 |
|------|------|
| GET | `/api/opui/webrtc/schema` |
| POST | `/api/opui/webrtc/offer` / `notify` |
| GET | `/api/opui/stream/health` |

### 引导

| 方法 | 路径 |
|------|------|
| GET | `/api/opui/onboarding` |
| PUT | `/api/opui/onboarding/accept_terms` / `complete` / `sunnylink` |

### PC 开发专用（`WEBUI_DEV_PC=1`）

| 方法 | 路径 |
|------|------|
| POST | `/api/opui/dev/preset/{preset}` |
| GET/POST | `/api/opui/dev/simulation` |

完整路由：`webui/server/routes/__init__.py`。

---

## 5. op助手 工具与工作流

| 工具 | 用途 |
|------|------|
| `webui_service_status` | :5080 是否监听 |
| `webui_health_check` | bootstrap + state + overlay |
| `webui_package_info` | VERSION、文档路径 |
| `webui_headless_status` | 无屏模式 API |
| `webui_onboarding_status` | 条款/训练是否完成 |
| `webui_qa_checklist` | 上车/PC 验收清单 |
| `webui_apply_dev_preset` | PC 模拟行车 HUD |
| `get_host_environment` | 车机/PC、Lite、硬件摘要 |
| `get_display_settings` / `set_display_settings` | 亮度等（有屏或 WebUI Display 面板） |
| `manager_control` | 重启 manager（改 `WebuiHeadlessMode` 后常需） |

### 推荐流程

**无屏首次配置**

1. `webui_service_status` → `webui_headless_status`
2. `webui_health_check` → 浏览器打开 URL
3. 完成 `webui_onboarding_status` 引导
4. Software → AGNOS（若 pending）
5. Network → 连 Wi-Fi

**无屏日常 / 排障**

1. `webui_health_check` + `GET /api/opui/system/manager_error`
2. 设置走 WebUI 或 op助手 `write_params`（**离路**）
3. 需要原生 ui 的行为 → 说明无屏不可用，改 WebUI

**验收**

- 技能 `webui-vehicle-qa` / `webui-development`
- `webui_report_template` 出报告

---

## 6. 安全（op助手）

- **行驶中**：WebUI 只读检查；`write_params`、OTA、AGNOS 安装、Wi-Fi 改密等需 **离路** + `confirm=true`
- **P0 overlay 验收**：静止或副驾，驾驶员勿操作屏幕
- 无屏设备勿建议依赖 `soundd`/驾驶员监控；Lite 用 `SpDevBeep`

---

## 7. 相关文档

| 路径 | 说明 |
|------|------|
| `ai/docs/COMMA_DEVICES.md` | C3/Lite/无屏 |
| `ai/docs/WEBUI_QA.md` | 验收索引 |
| `webui/docs/OP_ASSISTANT_HANDOFF.md` | 开发交接 |
| `webui/docs/VEHICLE_QA_CHECKLIST.md` | 上车清单 |
| `ai/skills/headless-webui/SKILL.md` | 技能入口 |
