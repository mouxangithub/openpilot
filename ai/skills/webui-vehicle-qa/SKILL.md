# WebUI 上车验收

## 何时使用

用户要求「WebUI 上车测试」「对照 scrcpy 验收」「overlay 对不对」「WebUI 验收报告」时启用。

## 前置

- 车机 `webui.webuid` 监听 **:5080**（或 PC 仅做 API 预检）
- 浏览器强刷 **`?v=78`**
- P0 overlay **必须**与 scrcpy 原生 UI 对照，PC mock 不能代替

## 步骤

1. `webui_package_info` — 版本与文档路径
2. `webui_headless_status` — 无屏设备确认 effective_headless
3. `webui_onboarding_status` — 若未完成引导，提示用户先完成条款/训练
3. `webui_service_status` — 端口与 PID
4. `webui_health_check(cache_bust=78)` — bootstrap / state / overlay
5. `webui_qa_checklist(scope=vehicle)` — P0/P1/P2
6. **P0**：对照 scrcpy（车道、路径、前车 chevron）— **唯一必须上车项**
7. **P1**：v78 动效（SLA 箭头、SCC 淡入、E2E 脉冲、底部 fade）可副驾目测
8. `webui_report_template` — 结构化 pass/fail 报告

工作流：`webui_vehicle_qa`

## 安全

- 行驶中只读，不写 Param
- 不要求驾驶员操作屏幕；副驾或离路执行 P0

## 相关文档

`webui/docs/OP_ASSISTANT_HANDOFF.md`、`webui/docs/VEHICLE_QA_CHECKLIST.md`
