# 一键健康检查

## 何时使用

用户问「为什么不能 engage」「系统是否正常」「帮我体检一下」「OTA 前检查」时，优先调用 **`run_health_check`**，再按结果逐项深入。

## 步骤

1. `run_health_check(scope=engage)` — 接合阻塞项（车辆状态、onroad 事件、告警、SecOC、CarParams）
2. 若 `overall=fail`：按 `checks[].action` 启用对应技能（`engage-troubleshooting`、`secoc-toyota`、`c3-dos-panda` 等）
3. `run_health_check(scope=system)` — 磁盘、Panda、网络
4. OTA / 更新前：`guide_ota_update` + `ota_preflight_checklist`

## 输出格式

- 用表格列出 `checks`：`status`（ok/warn/fail）、`summary`、`action`
- 不要输出完整 SecOCKey 或 API Key
- 行驶中仅只读检查，不写 Param

## 相关工具

`device_health`、`panda_status`、`network_diagnostics`、`read_onroad_events`、`get_vehicle_state`
