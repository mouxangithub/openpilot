# 系统健康

## 一键体检

用户要「体检」「健康检查」「为什么不能 engage」时，优先：

1. `run_health_check(scope=engage)` — 接合阻塞项
2. `run_health_check(scope=system)` — 磁盘 / Panda / 网络
3. `guide_ota_update` + `ota_preflight_checklist` — OTA 前

技能 **`health-check`**；工作流 **`health_check`**。

## 基础

`device_health`、`list_managed_processes`、`read_manager_log`、`grep_log`、`ota_status`

## Panda / C3 DOS

侧栏 **NO PANDA** 或 `panda_status` 无 `pandaStates`：

1. `panda_status` — 含 `usb_all`、`multi_panda`、`pandad_snapshot`、`firmware_path`
2. `list_all_pandas` — 每只 Panda 的 `hw_type_name` / internal / mcu
3. `panda_recovery_hint` — 双 Panda、USBErrorBusy 崩溃循环建议
4. `list_f4_pandas` — 仅 F4（内置 vs 外接黑熊）
5. offroad 刷 **F4**：`recover_dos_panda(confirm=true)` — 技能 **`c3-dos-panda`**
6. 双 USB 崩溃 → `rebuild_pandad(confirm=true)` — `updated` 或 pandad 源码变更后
7. 文档：`ai/docs/PANDA_FLASH.md`

**F4 固件**：`panda/board/obj/panda.bin.signed`。**H7 固件**：`panda/board/obj/panda_h7.bin.signed`。

## GitHub Runner / prebuilt CI

Actions **build** Pending 或用户问 prebuilt：

1. `github_runner_status`
2. `github_runner_recovery_hint`
3. 技能 **`github-runner`**；文档 `ai/docs/GITHUB_RUNNER.md`
