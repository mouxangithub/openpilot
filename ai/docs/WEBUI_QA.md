# WebUI 验收（op助手）

WebUI 运行在 **:5080**（`python3.12 -m webui.webuid` 或 PC `run_pc.py`）。

## 技能

| 技能 ID | 场景 |
|---------|------|
| `headless-webui` | **无屏**设备 WebUI 全功能、AGNOS/Wi-Fi/API |
| `webui-vehicle-qa` | 上车对照 scrcpy，P0 overlay |
| `webui-development` | PC 预览、Dev 预设、健康检查 |

## 工作流

- `webui_vehicle_qa` — 一键验收流程（见 `tools/domains/platform/workflows.py`）

## 工具

`webui_health_check`、`webui_service_status`、`webui_package_info`、`webui_qa_checklist`、`webui_report_template`、`webui_apply_dev_preset`（PC）、`webui_list_dev_presets`、`webui_onboarding_status`、`webui_headless_status`

## 文档（仓库内）

| 路径 | 说明 |
|------|------|
| `ai/docs/HEADLESS_WEBUI.md` | **无屏 + WebUI API/操作**（op助手 RAG） |
| `webui/docs/OP_ASSISTANT_HANDOFF.md` | 主交接手册 |
| `webui/docs/VEHICLE_QA_CHECKLIST.md` | 上车清单 |
| `webui/docs/TESTING_PC_DEVICE_SCRCPY.md` | PC / 车机 / scrcpy |
| `webui/docs/GUI_ALIGNMENT.md` | 对齐进度 v77 |

## 示例指令

```
请按 webui-vehicle-qa 执行验收：webui_health_check → webui_qa_checklist vehicle → P0 对照 scrcpy → webui_report_template
```
