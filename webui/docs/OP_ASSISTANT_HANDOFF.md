# WebUI ↔ op助手 上车测试交接手册

> **版本**：WebUI `0.4.7`（`?v=77`）  
> **角色**：开发者在 PC 抛光 → op助手 + 人类在车上按清单验收 → 反馈回开发

---

## 1. 架构共识

| 项 | 说明 |
|----|------|
| **画布** | 2160×1080 BIG UI（`openpilot/system/ui`） |
| **Web 栈** | WebRTC 摄像头 + WebGL/Canvas overlay + DOM HUD |
| **数据** | cereal / Params 经 `webui/server/bridge/*` |
| **P0 上车** | overlay 标定（车道线 / 彩虹路径 / 前车 chevron）— **唯一必须真机项** |
| **⛔ 不追求** | VisionIPC 像素 1:1、浏览器触控注入原生 raylib |

真画面投屏（独立项目）：见 `FUTURE_RAYLIB_UI_MIRROR.md`（若存在）。

---

## 2. 三阶段流程

### 阶段 A — PC 开发（开发者）

```bash
# Windows PC
py -3 E:\sp\webui\dev\run_pc.py --port 5080
# 浏览器 http://127.0.0.1:5080/?v=77
```

- Dev 面板预设：`onroad_overlay`、`confidence_low/high`、`onroad_engaged`
- 对照：`GUI_ALIGNMENT.md`、`GAP_VS_DEVICE.md`

### 阶段 B — 车机部署

```bash
python3.12 -m webui.webuid --host 0.0.0.0 --port 5080
```

- 同网段 PC 浏览器访问 `http://<车机IP>:5080/?v=77`
- scrcpy 投屏对照原生 UI

### 阶段 C — op助手验收

给 op助手示例指令：

> 请按 **webui-vehicle-qa** 技能执行 WebUI 上车验收：`webui_health_check` → `webui_qa_checklist vehicle` → P0 overlay 对照 scrcpy → `webui_report_template` 出报告

工作流 ID：`webui_vehicle_qa`

---

## 3. op助手工具

| 工具 | 用途 |
|------|------|
| `webui_package_info` | 读 VERSION 与文档路径 |
| `webui_service_status` | :5080 端口与 PID |
| `webui_health_check` | bootstrap / state / overlay API |
| `webui_qa_checklist` | 解析验收清单 |
| `webui_report_template` | 报告 Markdown 模板 |
| `webui_apply_dev_preset` | **仅 PC**（`WEBUI_DEV_PC=1`） |
| `webui_list_dev_presets` | Dev 预设列表（PC） |
| `webui_onboarding_status` | 条款/训练完成状态 |

---

## 4. 安全

- **行驶中**：只读检查，不写 Param，不触发 OTA / 刷机
- **P0 overlay**：需车辆静止或副驾操作，驾驶员勿分心
- overlay 偏差记录截图 + scrcpy 对照说明，勿猜测标定值

---

## 5. 相关文档

| 文档 | 说明 |
|------|------|
| [VEHICLE_QA_CHECKLIST.md](VEHICLE_QA_CHECKLIST.md) | 可打勾上车清单 |
| [TESTING_PC_DEVICE_SCRCPY.md](TESTING_PC_DEVICE_SCRCPY.md) | PC / 车机 / scrcpy 测试 |
| [GUI_ALIGNMENT.md](GUI_ALIGNMENT.md) | 对齐进度 |
| [GAP_VS_DEVICE.md](GAP_VS_DEVICE.md) | 管线级差异 |
| [../../ai/docs/WEBUI_QA.md](../../ai/docs/WEBUI_QA.md) | op助手侧索引 |
